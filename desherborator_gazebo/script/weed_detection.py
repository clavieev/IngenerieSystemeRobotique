#!/usr/bin/env python
import cv2 as cv2
import numpy as np
import matplotlib.pyplot as plt
import time
import sys
import os
import roslib

import rospy
from geometry_msgs.msg import Pose2D, Pose, Twist
from std_msgs.msg import Bool
from sensor_msgs.msg import Image
from gazebo_msgs.srv import SpawnModel, SpawnModelRequest, GetModelState
from cv_bridge import CvBridge, CvBridgeError




# Calcul the distance to the weed
def distance(h_reel, F,frame):
    # Coverte to hsv
    frame = np.uint8(frame)
    HSV = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)

    # Create the mask
    lower_green = np.array([50,100,50])
    upper_green = np.array([150, 255, 255])
    mask = cv2.inRange(HSV, lower_green, upper_green)

    # Find contours
    isolated = cv2.bitwise_and(frame, frame, mask=mask)
    version = int(cv2.__version__[0])
    if version == 3:
        im2, contours, hierachiy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if version == 4:
        contours, hierachiy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # Find minimum rectangle
    if len(contours) > 0:
        areas = [cv2.contourArea(c) for c in contours]
        max_index = np.argmax(areas)
        cnt = contour[max_index]
        x,y,w,h = cv2.boundingRect(cnt)
        dist = h_reel * F / h
    else:
        dist = 0
        cnt = None

    # Affichage
    #cv2.rectangle(img, (x,y), (x+w, y+h), (0, 255, 255), 2)
    #cv2.imshow("img",img)
    #time.sleep(10)
    return dist, cnt

#Calcul the angle
def WeedAngle(frame, cnt):

    frame = np.uint8(frame)
    height, width = frame.shape[:2]
    """
    #on parcourt le contour avec y_objet le plus grand (descend selon y et droite selon x)
    matrice = cnt[:,0,:]
    matrice_y = matrice[:,1]
    """

    #indice du point dont le x_objet est le plus grand
    try:
        x_objet, y_objet ,w,h = cv2.boundingRect(cnt)

        x_origine = width/2
        y_origine = height

        v1 = np.array([[width/2-x_origine],[0-y_origine]])
        v2 = np.array([[x_objet-x_origine],[y_objet-y_origine]])

        x1 = v1[0,0]
        y1 = v1[1,0]
        x2 = v2[0,0]
        y2 = v2[1,0]

        dot = x1*x2 + y1*y2      # dot product
        det = x1*y2 - y1*x2      # determinant
        angle = arctan2(det, dot)  # atan2(y, x) or atan2(sin, cos)
    except:
        angle = 0
    return angle

# change status of the weed alive => dead
def modif_couleur(request, xrbt, yrbt):
        PATH = sys.argv[1]
        urdf = ""
        with open(PATH+"box.urdf", "r") as stream:
            urdf = stream.read()

        urdf.replace("{xrbt}", str(xrbt))
        urdf.replace("{yrbt}", str(yrbt))

        request.model_name = "box"
        request.model_xml = urdf
        request.initial_pose.position.x = xrbt
        request.initial_pose.position.y = yrbt
        request.initial_pose.position.z = 0

        response = spawnModelService(request)
        if response.success:
            rospy.loginfo("Spawn_Success")
        else:
            rospy.logwarn(response.status_message)

class Block:
    def __init__(self, name, relative_entity_name):
        self._name = name
        self._relative_entity_name = relative_entity_name
        self._posex = 0
        self._posey = 0
        self._posez = 0
        self._orix = 0
        self._oriy = 0
        self._oriz = 0


    def gazebo_models(self):
        try:
            rospy.wait_for_service("/gazebo/get_model_state")
            model_coordinates = rospy.ServiceProxy('/gazebo/get_model_state', GetModelState)
            resp_coordinates = model_coordinates(self._name, "")

            self._posex = resp_coordinates.pose.position.x
            self._posey = resp_coordinates.pose.position.y
            self._posez = resp_coordinates.pose.position.z
            self._orix = resp_coordinates.pose.orientation.x
            self._oriy = resp_coordinates.pose.orientation.y
            self._oriz = resp_coordinates.pose.orientation.z
            #rospy.loginfo("{}".format(resp_coordinates))

        except rospy.ServiceException as e:
            rospy.loginfo("Get Model State service call failed:  {0}".format(e))

class image_converter:

  def __init__(self):

    self.bridge = CvBridge()
    self.image_sub = rospy.Subscriber("/main_camera/image_raw", Image, self.cb_cam)

  def cb_cam(self,data):
    try:
        cv_image = self.bridge.imgmsg_to_cv2(data, "rgb8")
        cv_image = np.uint8(cv_image)
    except CvBridgeError as e:
      print(e)


def cb_bool(msg):
    bool_weed_red = msg.data

##########################################################################
#                                                                        #
#                                   MAIN                                 #
#                                                                        #
##########################################################################

### Constantes
h_reel = 0.1
F = 1.3962634   #F = distance_objet(m) * hauteur pixel weed / hauteur reel objet(m)
cv_image = np.zeros((1280,720,3))


if __name__ == '__main__':
    ic = image_converter()
    rospy.init_node('dist_angle')

    # Publishers
    pub = rospy.Publisher('DistAngle', Pose2D, queue_size=10)
    distAngle = Pose2D()

    pub1 = rospy.Publisher('pose_robot', Pose, queue_size=10)
    pose_robot = Pose()

    # Subscribers
    rospy.Subscriber("/bool_action",Bool, cb_bool) #TODO

    # Services
    spawnModelService = rospy.ServiceProxy("/gazebo/spawn_urdf_model", SpawnModel)  # Spawn the boxes
    request = SpawnModelRequest()

    bobot = Block('desherborator', 'robot')

    rate = rospy.Rate(25)

    while not rospy.is_shutdown():
        #Calcul varibale
        bool_weed_red = 0
        dist, cnt = distance(h_reel, F, cv_image)
        theta = WeedAngle(cv_image, cnt)
        bobot.gazebo_models()
        #Publish
        distAngle.x = dist
        distAngle.theta = theta
        pub.publish(distAngle)

        pose_robot.position.x = bobot._posex
        pose_robot.position.y = bobot._posey
        pose_robot.position.z = bobot._posez
        pose_robot.orientation.x = bobot._orix
        pose_robot.orientation.y = bobot._oriy
        pose_robot.orientation.z = bobot._oriz
        pub1.publish(pose_robot)

        xrbt = bobot._posex + np.cos(bobot._oriz) * 0.26
        yrbt = bobot._posey + np.sin(bobot._oriz) * 0.26

        # Changement detat des weeds
        if bool_weed_red:
            modif_couleur(request, xrbt, yrbt)

        rate.sleep()
