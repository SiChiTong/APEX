#!/usr/bin/env python
import rospy
import json
from os.path import join
from rospkg import RosPack
from apex_playground.controller import Perception, Learning, Torso, Ergo, WorkManager, Recorder
from trajectory_msgs.msg import JointTrajectory
from re import search


class Controller(object):
    def __init__(self):
        self.rospack = RosPack()
        with open(join(self.rospack.get_path('apex_playground'), 'config', 'general.json')) as f:
            self.params = json.load(f)

        with open(join(self.rospack.get_path('apex_playground'), 'config', 'torso.json')) as f:
            self.torso_params = json.load(f)

        self.outside_ros = rospy.get_param('/use_sim_time', False)  # True if work manager <-> controller comm must use ZMQ
        id = search(r"(\d+)", rospy.get_namespace())
        self.worker_id = 0 if id is None else int(id.groups()[0])  # TODO string worker ID
        self.work = WorkManager(self.worker_id, self.outside_ros)
        self.torso = Torso()
        self.ergo = Ergo()
        self.learning = Learning()
        self.perception = Perception()
        self.recorder = Recorder()
        rospy.loginfo('Controller fully started!')

    def run(self):
        work = self.work.get()
        if not work.work_available:
            return

        rospy.set_param('experiment/current/task', work.task)
        rospy.set_param('experiment/current/trial', work.trial)
        rospy.set_param('experiment/current/method', work.method)

        for iteration in range(work.iteration, work.num_iterations):
            if iteration % self.params["ergo_reset"] == 0:
                self.ergo.reset()
            try:
                rospy.set_param('experiment/current/iteration', iteration)
                if not rospy.is_shutdown():
                    self.execute_iteration(work.task, work.method, iteration, work.trial, work.num_iterations)
            finally:
                abort = self.work.update(work.task, work.trial, iteration).abort
                if abort:
                    rospy.logwarn("Work manager requested abortion, closing...")
                    return
        rospy.loginfo("Work successfully terminated, closing...")

    def execute_iteration(self, task, method, iteration, trial, num_iterations):
        rospy.logwarn("Controller starts iteration {} {}/{} trial {}".format(method, iteration+1, num_iterations, trial))

        if self.perception.help_pressed():
            rospy.sleep(1.5)  # Wait for the robot to fully stop
            self.recorder.record(task, method, trial, iteration)
            recording = self.perception.record(human_demo=True, nb_points=self.params['nb_points'])
            self.torso.set_torque_max(self.torso_params['torques']['reset'])
            self.torso.reset(slow=True)
        else:
            trajectory = self.learning.produce().torso_trajectory
            self.torso.set_torque_max(self.torso_params['torques']['motion'])
            self.recorder.record(task, method, trial, iteration)
            self.torso.execute_trajectory(trajectory)  # TODO: blocking, non-blocking, action server?
            recording = self.perception.record(human_demo=False, nb_points=self.params['nb_points'])
            recording.demo.torso_demonstration = JointTrajectory()
            self.torso.set_torque_max(80)
            self.torso.reset(slow=False)
        success = self.learning.perceive(recording.demo)  # TODO non-blocking

if __name__ == '__main__':
    rospy.init_node("controller")
    Controller().run()
