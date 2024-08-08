import os
import rospy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Int32
from cv_bridge import CvBridge, CvBridgeError
import cv2
import numpy as np
import tensorflow as tf
import threading
import queue

class BirdDetection:
    def __init__(self):
        rospy.init_node('detection_1', anonymous=True)
        self.bridge = CvBridge()
        self.image_sub = rospy.Subscriber('/usb_cam1/image_compressed', CompressedImage, self.callback)
        self.trigger_pub = rospy.Publisher('/detection_1/is_triggered', Int32, queue_size=10)
        self.detection_model = self.load_model()

        # 이미지 표시를 위한 큐와 스레드 초기화
        self.display_queue = queue.Queue()
        self.display_thread = threading.Thread(target=self.display_images)
        self.display_thread.start()

    def load_model(self):
        script_dir = os.path.dirname(__file__)
        model_dir = os.path.join(script_dir, '..', 'models', 'ssd_mobilenet_v2_fpnlite_320x320_coco17_tpu-8', 'saved_model')
        model_dir = os.path.abspath(model_dir)
        model = tf.saved_model.load(model_dir)
        return model

    def callback(self, data):
        try:
            # 압축된 이미지를 CV2 이미지로 변환
            np_arr = np.frombuffer(data.data, np.uint8)
            cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            image_resized = cv2.resize(cv_image, (320, 320))  # 모델 입력 크기에 맞게 조정
            input_tensor = tf.convert_to_tensor(image_resized)
            input_tensor = input_tensor[tf.newaxis, ...]

            # 객체 감지 수행
            output_dict = self.detection_model(input_tensor)
            num_detections = int(output_dict['num_detections'][0])
            boxes = output_dict['detection_boxes'][0].numpy()
            class_ids = output_dict['detection_classes'][0].numpy().astype(int)
            scores = output_dict['detection_scores'][0].numpy()

            bird_detected = False
            for i in range(num_detections):
                if scores[i] > 0.3 and class_ids[i] == 16:  # 'bird' 클래스 확인
                    box = boxes[i]
                    ymin, xmin, ymax, xmax = box
                    left, right, top, bottom = (xmin * cv_image.shape[1], xmax * cv_image.shape[1],
                                                ymin * cv_image.shape[0], ymax * cv_image.shape[0])
                    
                    # 바운딩 박스와 점수 그리기
                    cv_image = cv2.rectangle(cv_image, (int(left), int(top)), (int(right), int(bottom)), (255, 0, 0), 2)
                    score_text = f"Score: {scores[i]:.2f}"
                    cv_image = cv2.putText(cv_image, score_text, (int(left), int(top) - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    cv_image = cv2.putText(cv_image, "Detect!", (int(left), int(top) - 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    
                    bird_detected = True

            # 트리거 신호 발행
            if bird_detected:
                self.trigger_pub.publish(1)
            else:
                self.trigger_pub.publish(0)

            # 이미지 큐에 추가
            self.display_queue.put(cv_image)

        except CvBridgeError as e:
            rospy.logerr(f"CvBridge Error: {e}")
        except Exception as e:
            rospy.logerr(f"Callback 예외: {e}")

    def display_images(self):
        while not rospy.is_shutdown():
            if not self.display_queue.empty():
                cv_image = self.display_queue.get()
                cv2.imshow("Bird Detection", cv_image)
                cv2.waitKey(1)  # OpenCV 창 갱신

    def run(self):
        rospy.spin()
        cv2.destroyAllWindows()  # ROS 노드 종료 시 OpenCV 창 닫기

if __name__ == '__main__':
    detector = BirdDetection()
    detector.run()

