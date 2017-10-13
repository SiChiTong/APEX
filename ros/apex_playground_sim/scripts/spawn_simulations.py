#!/usr/bin/env python
import argparse
import time
from signal import SIGINT, signal
from rospkg import RosPack
from subprocess import Popen
from os.path import isfile, join, realpath
from os import remove, environ
from shutil import copy2
from termcolor import colored


def get_vrep_api_file(*ports):
    def open_port(port_id, port):
        return """
portIndex{0}_port             = {1}
portIndex{0}_debug            = false
portIndex{0}_syncSimTrigger   = true
               """.format(port_id, port)
    remote_api_str = "\n".join([open_port(port_id + 1, port) for port_id, port in enumerate(ports)])
    return remote_api_str

class SimulationSpawner(object):
    """
    This script spawns the request number of simulated APEX experiments in different V-REP instances
    All experiments are distributed in different ROS namespaces named /instance_XX/
    They will all read the unique experiment status and select work as it comes
    """
    def __init__(self, num_instances, vrep_binary_path, vrep_connection_path, headless):
        self.rospack = RosPack()
        self.vrep_con_path = vrep_connection_path
        self.vrep_con_path_bak = vrep_con_path + '.bak'
        self.vrep_bin_path = vrep_binary_path
        self.num_instances = num_instances
        self.headless = headless
        self.running_instances = []  # stores True if the corresponding ROS+Vrep instance is running
        self.children = []  # All children processes
        self.ros_children = []  # Only ROS children processes
        self.vrep_children = []  # Only simulator processes
        self.running = False

        # PORTS
        # Warning: Only the work manager runs on ROS master 11311
        self.initial_ros_master_port = 11400
        self.initial_ui_port = 5000
        self.initial_vrep_port = 46400

    def signal_handler(self, signal, frame):
        self.running = False

    def run(self):
        self.running = True
        copy2(self.vrep_con_path, self.vrep_con_path_bak)

        # Start the Work Manager
        print(colored("### Launching the work manager on ROS master {}".format(environ['ROS_MASTER_URI']), 'blue'))
        process_str = 'roscore'
        print(colored(process_str, 'yellow'))
        process = Popen(process_str.split(' '))
        self.children.append(process)
        process_str = 'rosrun apex_playground work_manager.py --comm-outside-ros'
        print(colored(process_str, 'yellow'))
        process = Popen(process_str.split(' '))
        self.children.append(process)

        try:
            for n in range(self.num_instances):
                if not self.running: return
                print(colored("### Launching simulated instance {}/{}".format(n+1, self.num_instances), 'blue'))
                ros_master_port = self.initial_ros_master_port + n
                ros_master_uri = 'http://localhost:{}'.format(ros_master_port)
                environ['ROS_MASTER_URI'] = ros_master_uri

                vrep_clock_port = self.initial_vrep_port + n*10
                vrep_env_port = self.initial_vrep_port + n*10 + 1
                vrep_torso_port = self.initial_vrep_port + n*10 + 2
                vrep_ergo_port = self.initial_vrep_port + n*10 + 3

                ui_port = self.initial_ui_port + n

                print(colored("[ROS master URI] {}".format(ros_master_uri), 'green'))
                print(colored("[VREP ports] clock : {} environment : {} torso : {} ergo : {}".format(vrep_clock_port,
                                                                                             vrep_env_port,
                                                                                             vrep_torso_port,
                                                                                             vrep_ergo_port), 'green'))
                print(colored("[Web UI] port : {}".format(ui_port), 'green'))
                with open(self.vrep_con_path, 'w') as f:
                    f.write(get_vrep_api_file(vrep_clock_port, vrep_env_port, vrep_torso_port, vrep_ergo_port))

                scene = join(self.rospack.get_path('apex_playground_sim'), 'simulation', 'models', 'apex_playground.ttt')
                process_str = '{} {}{}'.format(self.vrep_bin_path, '-h ' if self.headless else '', scene)
                print(colored(process_str, 'yellow'))

                if not isfile(scene):
                    raise IOError("Scene file {} does not exist".format(scene))

                process = Popen(process_str.split(' '))
                self.children.append(process)
                self.vrep_children.append(process)

                time.sleep(10)  # Let time to V-Rep to load the scene

                name = 'apex_{}'.format(n)
                process_str = 'roslaunch apex_playground_sim start_sim.launch namespace:={} ' \
                              'start_manager:=false ' \
                              'clock_vrep_port:={} environment_vrep_port:={} torso_vrep_port:={} ' \
                              'ergo_vrep_port:={} ui_port:={}'.format(name, vrep_clock_port,
                                                                vrep_env_port,
                                                                vrep_torso_port,
                                                                vrep_ergo_port, ui_port)
                print(colored(process_str, 'yellow'))
                process = Popen(process_str.split(' '), env=environ)
                self.children.append(process)
                self.ros_children.append(process)
                self.running_instances.append(True)

            while self.running:
                print(colored("Instances running? {}".format(self.running_instances), 'blue'))
                for i, p in enumerate(self.ros_children):
                    if self.running_instances[i] and p.poll() is not None:
                        # if ROS process has closed or crashed, close the corresponding simulation instance
                        print(colored("ROS process {} has terminated, closing simulator...".format(i), 'red'))
                        self.running_instances[i] = False
                        self.vrep_children[i].terminate()
                if len([running for running in self.running_instances if running]) == 0:
                    break
                time.sleep(2)

        finally:
            for p in self.children:
                try:
                    p.send_signal(SIGINT)
                except OSError:
                    pass

            copy2(self.vrep_con_path_bak, self.vrep_con_path)
            #remove(self.vrep_con_path_bak)

            for i, p in enumerate(self.children):
                if p.poll() is not None:
                    print(colored('Waiting process {} to close...'.format(i), 'red'))
                    p.wait()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Launch V-REP, ROS master and ROS nodes to simulate N apex setups in parallel.")

    parser.add_argument('--vrep-path',
                        type=str,
                        required=True,
                        nargs='?',
                        help='Path to the root of the V-REP simulator, e.g. /home/user/V-REP/')

    parser.add_argument('-n', '--number',
                        type=int,
                        default=1,
                        nargs='?',
                        help='Number of simultaneous experiments (instances)')

    parser.add_argument('--headless',
                        action='store_true',
                        help='VRep headless')

    args = parser.parse_known_args()[0]

    vrep_bin_path = realpath(join(args.vrep_path, 'vrep.sh'))
    vrep_con_path = realpath(join(args.vrep_path, 'remoteApiConnections.txt'))
    for file in [vrep_bin_path, vrep_con_path]:
        if not isfile(vrep_bin_path):
            raise ValueError("Not found: {} \n"
                             "Set argument --vrep-path or vrep-path:= pointing to the dir containing vrep.sh".format(file))

    if args.number not in range(1, 100):
        raise ValueError("Set argument -n as the number of instances to start")

    s = SimulationSpawner(args.number, vrep_bin_path, vrep_con_path, args.headless)
    signal(SIGINT, s.signal_handler)
    s.run()
