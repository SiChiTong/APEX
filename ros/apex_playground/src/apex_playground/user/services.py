import rospy
from numpy import array
from apex_playground.srv import SetIteration, SetIterationRequest, SetFocus, SetFocusRequest, Assess, AssessRequest, GetInterests, GetInterestsRequest
from std_msgs.msg import String, Bool, UInt32


class UserServices(object):
    def __init__(self):
        self.services = {'set_iteration': {'name': 'learning/set_iteration', 'type': SetIteration},
                         'set_focus': {'name': 'learning/set_interest', 'type': SetFocus},
                         'assess': {'name': 'controller/assess', 'type': Assess},
                         'get_interests': {'name': 'learning/get_interests', 'type': GetInterests}}

        rospy.Subscriber('learning/current_focus', String, self._cb_focus)
        rospy.Subscriber('learning/user_focus', String, self._cb_user_focus)
        rospy.Subscriber('learning/ready_for_interaction', Bool, self._cb_ready)

        self.current_focus = ""
        self.user_focus = ""
        self.ready_for_interaction = False

        for service_name, service in self.services.items():
            rospy.loginfo("User node is waiting service {}...".format(service['name']))
            rospy.wait_for_service(service['name'])
            service['call'] = rospy.ServiceProxy(service['name'], service['type'])

        rospy.loginfo("User node started!")

    @property
    def interests(self):
        call = self.services['get_interests']['call']
        response = call(GetInterestsRequest())
        interests = dict(zip(response.names, array(map(lambda x: x.data, response.interests)).reshape(response.num_iterations.data, len(response.names)).T.tolist()))
        return interests

    def _cb_focus(self, msg):
        self.current_focus = msg.data

    def _cb_user_focus(self, msg):
        self.user_focus = msg.data

    def _cb_ready(self, msg):
        self.ready_for_interaction = msg.data

    def set_focus(self, space):
        call = self.services['set_focus']['call']
        return call(SetFocusRequest(space=space))

    def assess(self, assessment):
        call = self.services['assess']['call']
        return call(AssessRequest(goal=assessment))

    def set_iteration(self, iteration):
        call = self.services['set_iteration']['call']
        return call(SetIterationRequest(iteration=UInt32(data=int(iteration))))
