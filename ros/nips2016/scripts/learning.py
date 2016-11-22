#!/usr/bin/env python

import rospy
import os
import json
from os.path import join
from rospkg.rospack import RosPack
from nips2016.srv import Perceive, Produce, ProduceResponse, PerceiveResponse, GetSensorialState, GetSensorialStateRequest
from nips2016.learning import EnvironmentTranslator, Learning


class LearningNode(object):
    def __init__(self):
        self.rospack = RosPack()
        with open(join(self.rospack.get_path('nips2016'), 'config', 'learning.json')) as f:
            self.params = json.load(f)

        self.translator = EnvironmentTranslator()
        self.learning = Learning(self.translator.config, 
                                 n_motor_babbling=self.params["n_motor_babbling"], 
                                 explo_noise=self.params["explo_noise"], 
                                 choice_eps=self.params["choice_eps"])
        self.learning.start()
        self.experiment_name = rospy.get_param("/nips2016/experiment_name", "experiment")

        # Serving these services
        self.service_name_perceive = "/nips2016/learning/perceive"
        self.service_name_produce = "/nips2016/learning/produce"
        # Using these services

        self.service_name_get_perception = "/nips2016/perception/get"
        for service in [self.service_name_get_perception]:
            rospy.loginfo("Learning  node is waiting service {}...".format(service))
            rospy.wait_for_service(service)
        self.get_state = rospy.ServiceProxy(self.service_name_get_perception, GetSensorialState)

    def run(self):
        rospy.Service(self.service_name_perceive, Perceive, self.cb_perceive)
        rospy.Service(self.service_name_produce, Produce, self.cb_produce)
        rospy.loginfo("Learning is up!")
        rospy.spin()

    def save(self):
        dir = join(self.rospack.get_path('nips2016'), 'logs')
        if not os.path.isdir(dir):
            os.makedirs(dir)
        self.learning.save(dir, self.experiment_name)

    ################################# Service callbacks
    def cb_perceive(self, request):
        s = self.translator.sensory_trajectory_msg_to_list(request.sensorial_demonstration)
        if len(request.torso_demonstration.points) > 0:
            torso_traj = self.translator.trajectory_msg_to_matrix(request.torso_demonstration)
            torso_traj_w = self.translator.trajectory_to_w(torso_traj)
            rospy.loginfo("Learning node is perceiving sensory + torso trajectories")
            self.learning.perceive(s, m_demo=torso_traj_w)
        else:
            rospy.loginfo("Learning node is perceiving sensory trajectory only")
            self.learning.perceive(s)

        # Regularly overwrite the results
        if self.learning.get_iterations() % self.params['save_every'] == 0:
            self.save()
        return PerceiveResponse()

    def cb_produce(self, request):
        rospy.loginfo("Learning node is requesting the current state")
        state = self.get_state(GetSensorialStateRequest()).state
        rospy.loginfo("Learning node is producing...")
        w = self.learning.produce(self.translator.get_context(state))
        trajectory_matrix = self.translator.w_to_trajectory(w)
        trajectory_msg = self.translator.matrix_to_trajectory_msg(trajectory_matrix)
        response = ProduceResponse(torso_trajectory=trajectory_msg)
        return response

if __name__ == '__main__':
    rospy.init_node('learning')
    LearningNode().run()

