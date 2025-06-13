import cv2
import logging
import argparse
import warnings
import numpy as np
from collections import deque
import json
import os

import torch
import torch.nn.functional as F
from torchvision import transforms

from config import data_config
from utils.helpers import get_model, draw_bbox_gaze
from ultralytics import YOLO

import uniface

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format='%(message)s')


class PostureAnalyzer:
    def __init__(self, window_duration=3.0, fps=30, skip=3):
        self.window_duration = window_duration
        self.fps = fps
        self.skip = skip  # Skip frames for analysis, e.g., every 3rd frame
        self.window_size = int(window_duration * fps / self.skip)  # 120 frames for 4 seconds at 30fps
        
        # Sliding window data storage
        self.pose_data = deque(maxlen=self.window_size)
        self.gaze_data = deque(maxlen=self.window_size)
        self.bbox_data = deque(maxlen=self.window_size)
        self.frame_numbers = deque(maxlen=self.window_size)
        
        # Current frame counter
        self.current_frame = 0
        
        # Thresholds for posture detection (in ratios)
        self.YAW_DOWN_THRESHOLD = -0.25      # Looking down (radians)
        self.BODY_SWAY_RATIO = 0.15          # Body sway relative to bbox width
        self.HEAD_TILT_THRESHOLD = 0.25       # Head tilt angle threshold
        self.HAND_EYE_RATIO = 0.25           # Hand-to-eye distance relative to bbox width
        
        # Tracking current states
        self.current_states = {
            'gaze_down': False,
            'body_sway': False,
            'head_tilt': False,
            'hand_on_face': False,
            'turned_away': False,
        }
        
        # Tracking action periods
        self.action_periods = {
            'gaze_down': [],
            'body_sway': [],
            'head_tilt': [],
            'hand_on_face': [],
            'turned_away': [],
        }
        
        # Current ongoing actions (start frame recorded, waiting for end)
        self.ongoing_actions = {}
        
    def add_frame_and_analyze(self, pose_keypoints, gaze_pitch, gaze_yaw, person_bbox):
        """Add frame data and perform real-time analysis"""
        self.current_frame += 1
        
        # Add data to sliding window
        self.pose_data.append(pose_keypoints)
        self.gaze_data.append((gaze_pitch, gaze_yaw))
        self.bbox_data.append(person_bbox)
        self.frame_numbers.append(self.current_frame)
        
        # Perform analysis if we have enough data
        if len(self.pose_data) >= min(30, self.window_size):  # At least 1 second of data
            detected_actions = self.analyze_current_window()
            
            # Print currently detected actions
            if detected_actions:
                print(f"Frame {self.current_frame}: {', '.join(detected_actions)}")
            
            # Update state tracking
            self.update_action_tracking(detected_actions)
    
    def analyze_current_window(self):
        """Analyze current window and return list of detected actions"""
        detected = []
        
        # 1. Head down detection
        if self.detect_gaze_down():
            detected.append("시선을 아래로")
        
        # 2. Body swaying detection
        if self.detect_body_swaying():
            detected.append("좌우로 몸 흔들기")
        
        # 3. Head tilting detection
        if self.detect_head_tilting():
            detected.append("고개 기울이기")
        
        # 4. Hand to face detection
        if self.detect_hand_to_face():
            detected.append("머리나 얼굴 긁기")
        
        # 5. Turned away detection
        if self.detect_turned_away():
            detected.append("뒤돌아선 채로 있기")
        
        return detected
    
    def update_action_tracking(self, detected_actions):
        """Update tracking of action start/end points"""
        action_map = {
            "시선을 아래로": "gaze_down",
            "좌우로 몸 흔들기": "body_sway", 
            "고개 기울이기": "head_tilt",
            "머리나 얼굴 긁기": "hand_on_face",
            "뒤돌아선 채로 있기": "turned_away",
        }
        
        current_detected_keys = set()
        for action in detected_actions:
            if action in action_map:
                current_detected_keys.add(action_map[action])
        
        # Check each possible action
        for action_key in action_map.values():
            was_active = self.current_states[action_key]
            is_active = action_key in current_detected_keys
            
            if not was_active and is_active:
                # Action started
                start_frame = max(1, self.current_frame - self.window_size)
                self.ongoing_actions[action_key] = start_frame
                print(f"🔴 {self.get_action_name(action_key)} 시작: {start_frame}프레임")
                
            elif was_active and not is_active:
                # Action ended
                if action_key in self.ongoing_actions:
                    start_frame = self.ongoing_actions[action_key]
                    end_frame = max(1, self.current_frame - self.window_size)
                    self.action_periods[action_key].append((start_frame, end_frame))
                    del self.ongoing_actions[action_key]
                    print(f"🟢 {self.get_action_name(action_key)} 종료: {end_frame}프레임")
            
            # Update current state
            self.current_states[action_key] = is_active
    
    def get_action_name(self, action_key):
        """Convert action key to Korean name"""
        names = {
            'gaze_down': '시선을 아래로',
            'body_sway': '좌우로 몸 흔들기',
            'head_tilt': '고개 기울이기', 
            'hand_on_face': '머리나 얼굴 긁기',
            'turned_away': '뒤돌아선 채로 있기',
        }
        return names.get(action_key, action_key)
    
    def finalize_analysis(self):
        """Finalize any ongoing actions and prepare final report"""
        # End any ongoing actions
        for action_key, start_frame in self.ongoing_actions.items():
            end_frame = self.current_frame
            self.action_periods[action_key].append((start_frame, end_frame))
            print(f"🟡 {self.get_action_name(action_key)} 종료 (영상 끝): {end_frame}프레임")
        
        self.ongoing_actions.clear()
    
    def print_final_statistics(self, save_json=True, json_filename="posture_analysis_result.json"):
        """Print comprehensive statistics of detected actions and save to JSON"""
        print("\n" + "="*50)
        print("📊 발표 자세 분석 최종 결과")
        print("="*50)
        
        total_actions = sum(len(periods) for periods in self.action_periods.values())
        
        # Prepare data for JSON export
        json_data = {
            "summary": {
                "total_bad_postures": total_actions,
                "total_duration_seconds": 0,
                "analysis_settings": {
                    "window_duration": self.window_duration,
                    "fps": self.fps,
                    "skip_frames": self.skip
                }
            },
            "detected_actions": {}
        }
        
        if total_actions == 0:
            print("✅ 문제가 되는 자세가 발견되지 않았습니다!")
            json_data["summary"]["message"] = "문제가 되는 자세가 발견되지 않았습니다"
        else:
            print(f"총 {total_actions}개의 나쁜 자세 구간이 탐지되었습니다.\n")
            
            total_duration_frames = 0
            
            for action_key, periods in self.action_periods.items():
                if periods:
                    action_name = self.get_action_name(action_key)
                    print(f"📌 {action_name}:")
                    
                    # Prepare JSON data for this action
                    json_data["detected_actions"][action_key] = {
                        "action_name": action_name,
                        "periods": []
                    }
                    
                    action_total_duration = 0
                    for i, (start, end) in enumerate(periods, 1):
                        # Adjust for skipped frames
                        actual_start = start * self.skip
                        actual_end = end * self.skip
                        duration = actual_end - actual_start + 1
                        action_total_duration += duration
                        duration_sec = duration / self.fps
                        
                        print(f"   구간 {i}: {actual_start}프레임 - {actual_end}프레임 ({duration_sec:.1f}초)")
                        
                        # Add to JSON data
                        json_data["detected_actions"][action_key]["periods"].append({
                            "start_frame": int(actual_start),
                            "end_frame": int(actual_end),
                            "duration_frames": int(duration),
                            "duration_seconds": round(duration_sec, 1)
                        })
                    
                    total_duration_frames += action_total_duration
                    action_total_sec = action_total_duration / self.fps
                    print(f"   총 지속 시간: {action_total_sec:.1f}초 ({len(periods)}회 발생)\n")
                    
                    # Add summary to JSON
                    json_data["detected_actions"][action_key]["summary"] = {
                        "total_duration_seconds": round(action_total_sec, 1),
                        "occurrence_count": len(periods)
                    }
            
            # Update total duration in summary
            total_duration_sec = total_duration_frames / self.fps
            json_data["summary"]["total_duration_seconds"] = round(total_duration_sec, 1)
        
        # Save to JSON file
        if save_json:
            try:
                with open(json_filename, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                print(f"📄 분석 결과가 '{json_filename}' 파일로 저장되었습니다.")
            except Exception as e:
                print(f"⚠️ JSON 파일 저장 중 오류 발생: {e}")
        
        return json_data
    
    def detect_gaze_down(self):
        """Detect if head is looking down for majority of window"""
        down_count = 0
        for _, gaze_yaw in self.gaze_data:
            if gaze_yaw is not None and gaze_yaw < self.YAW_DOWN_THRESHOLD:
                down_count += 1
        
        # If looking down for more than 60% of the window
        return down_count > len(self.gaze_data) * 0.6
    
    def detect_body_swaying(self):
        """Detect left-right body swaying using body keypoints movement analysis"""
        if len(self.pose_data) < 10:
            return False
        
        body_centers = []
        bbox_widths = []
        
        # Extract body center positions from each frame
        for i, pose in enumerate(self.pose_data):
            if pose is not None and len(pose) > 12 and self.bbox_data[i] is not None:
                # Get body keypoints: shoulders (5,6) and hips (11,12)
                left_shoulder = pose[5]
                right_shoulder = pose[6]
                left_hip = pose[11]
                right_hip = pose[12]
                
                # Check if shoulders have good confidence
                if left_shoulder[2] > 0.5 and right_shoulder[2] > 0.5:
                    # Try to use both shoulders and hips if available
                    if left_hip[2] > 0.5 and right_hip[2] > 0.5:
                        # Calculate body center using shoulders and hips (full torso)
                        body_center_x = (left_shoulder[0] + right_shoulder[0] + left_hip[0] + right_hip[0]) / 4
                    else:
                        # Fall back to shoulders only (for sitting cases)
                        body_center_x = (left_shoulder[0] + right_shoulder[0]) / 2
                    
                    body_centers.append(body_center_x)
                    
                    # Get bounding box width for normalization
                    bbox = self.bbox_data[i]
                    bbox_width = bbox[2] - bbox[0] if bbox[2] > bbox[0] else 100
                    bbox_widths.append(bbox_width)
        
        if len(body_centers) < 10:  # Need at least 10 frames for analysis
            return False
        
        # Calculate position changes between consecutive frames
        position_changes = []
        
        for i in range(1, len(body_centers)):
            bbox_width = bbox_widths[i]
            # Normalize position change by bbox width
            change = (body_centers[i] - body_centers[i-1]) / bbox_width
            position_changes.append(change)
        
        if len(position_changes) == 0:
            return False
        
        # Calculate sum of changes and sum of absolute changes
        sum_of_changes = sum(position_changes)
        sum_of_abs_changes = sum(abs(change) for change in position_changes)
        
        # If sum of absolute changes is much larger than sum of changes,
        # it indicates oscillatory movement (swaying)
        if sum_of_abs_changes == 0:
            return False
        
        # Calculate ratio: how much the movements cancel each other out
        cancellation_ratio = abs(sum_of_changes) / sum_of_abs_changes
        
        # If movements largely cancel out (ratio close to 0) and there's significant movement,
        # it indicates swaying
        is_swaying = (cancellation_ratio < 0.2 and  # Movements cancel each other out
                    sum_of_abs_changes > self.BODY_SWAY_RATIO)  # But there's significant movement
        
        return is_swaying
    
    def detect_head_tilting(self):
        """Detect if head is consistently tilted using face keypoints"""
        tilt_angles = []
        
        for pose in self.pose_data:
            if pose is not None and len(pose) > 4:
                left_eye = pose[1]
                right_eye = pose[2]
                
                if left_eye[2] > 0.5 and right_eye[2] > 0.5:
                    # Calculate angle between eyes
                    dx = right_eye[0] - left_eye[0]
                    dy = right_eye[1] - left_eye[1]
                    
                    if dx != 0:  # Avoid division by zero
                        angle = np.arctan2(dx, dy) + np.pi / 2  # Adjust to match tilt direction
                        tilt_angles.append(abs(angle))
                        # print(f"Detected tilt angle: {angle:.2f} degrees")
        
        if len(tilt_angles) < 5:
            return False
        
        avg_tilt = np.mean(tilt_angles)
        return avg_tilt > self.HEAD_TILT_THRESHOLD
    
    def detect_hand_to_face(self):
        """Detect if hands are frequently near eyes area"""
        hand_on_face_count = 0
        
        for i, pose in enumerate(self.pose_data):
            if pose is not None and len(pose) > 10 and self.bbox_data[i] is not None:
                # Get eye positions
                left_eye = pose[1]
                right_eye = pose[2]
                left_ear = pose[3]
                right_ear = pose[4]
                left_wrist = pose[9]
                right_wrist = pose[10]
                
                # Get bounding box width for normalization
                bbox = self.bbox_data[i]
                bbox_width = bbox[2] - bbox[0] if bbox[2] > bbox[0] else 100
                
                hand_near_face = False
                
                # Check left hand to left eye distance
                if left_eye[2] > 0.5 and left_wrist[2] > 0.5:
                    dist_left = np.sqrt((left_wrist[0] - left_eye[0])**2 + (left_wrist[1] - left_eye[1])**2)
                    normalized_dist_left = dist_left / bbox_width
                    dist_left_ear = np.sqrt((left_wrist[0] - left_ear[0])**2 + (left_wrist[1] - left_ear[1])**2)
                    normalized_dist_left_ear = dist_left_ear / bbox_width
                    normalized_dist_left = min(normalized_dist_left, normalized_dist_left_ear)

                    if normalized_dist_left < self.HAND_EYE_RATIO:
                        hand_near_face = True
                
                # Check right hand to right eye distance
                if right_eye[2] > 0.5 and right_wrist[2] > 0.5:
                    dist_right = np.sqrt((right_wrist[0] - right_eye[0])**2 + (right_wrist[1] - right_eye[1])**2)
                    normalized_dist_right = dist_right / bbox_width
                    dist_right_ear = np.sqrt((right_wrist[0] - right_ear[0])**2 + (right_wrist[1] - right_ear[1])**2)
                    normalized_dist_right_ear = dist_right_ear / bbox_width
                    normalized_dist_right = min(normalized_dist_right, normalized_dist_right_ear)

                    if normalized_dist_right < self.HAND_EYE_RATIO:
                        hand_near_face = True
                
                if hand_near_face:
                    hand_on_face_count += 1
        
        # If hands near face for more than 10% of window
        return hand_on_face_count > len(self.pose_data) * 0.1
    
    def detect_turned_away(self):
        """Detect if person is turned away from camera using shoulder keypoint order"""
        turned_count = 0
        
        for pose in self.pose_data:
            if pose is not None and len(pose) > 6:
                left_shoulder = pose[6]   # Left shoulder keypoint
                right_shoulder = pose[5]  # Right shoulder keypoint
                
                # Both shoulders must be visible with good confidence
                if left_shoulder[2] > 0.5 and right_shoulder[2] > 0.5:
                    left_x = left_shoulder[0]
                    right_x = right_shoulder[0]
                    
                    # When facing camera: left_shoulder.x < right_shoulder.x
                    # When turned away: left_shoulder.x > right_shoulder.x (shoulders appear flipped)
                    if left_x > right_x:
                        turned_count += 1
        
        # If turned away for more than 50% of window
        return turned_count > len(self.pose_data) * 0.5
    
    def get_results(self):
        """Get all detected action periods"""
        return self.action_periods
    
    def print_results(self):
        """Legacy method - use print_final_statistics instead"""
        self.print_final_statistics()


def parse_args():
    parser = argparse.ArgumentParser(description="Gaze estimation inference with posture analysis")
    parser.add_argument("--model", type=str, default="mobilenetv2", help="Model name, default `resnet18`")
    parser.add_argument(
        "--weight",
        type=str,
        default="weights/mobilenetv2.pt",
        help="Path to gaze esimation model weights"
    )
    parser.add_argument("--view", action="store_true", default=True, help="Display the inference results")
    parser.add_argument("--source", type=str, default="assets/in_video.mp4",
                        help="Path to source video file or camera index")
    parser.add_argument("--output", type=str, default="output.mp4", help="Path to save output file")
    parser.add_argument("--dataset", type=str, default="gaze360", help="Dataset name to get dataset related configs")
    parser.add_argument("--json-output", type=str, default="posture_analysis_result.json", 
                    help="Path to save JSON analysis results")
    args = parser.parse_args()

    # Override default values based on selected dataset
    if args.dataset in data_config:
        dataset_config = data_config[args.dataset]
        args.bins = dataset_config["bins"]
        args.binwidth = dataset_config["binwidth"]
        args.angle = dataset_config["angle"]
    else:
        raise ValueError(f"Unknown dataset: {args.dataset}. Available options: {list(data_config.keys())}")

    return args


def pre_process(image):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize(448),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    image = transform(image)
    image_batch = image.unsqueeze(0)
    return image_batch


def main(params):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    idx_tensor = torch.arange(params.bins, device=device, dtype=torch.float32)

    face_detector = uniface.RetinaFace()  # third-party face detection library

    try:
        gaze_detector = get_model(params.model, params.bins, inference_mode=True)
        state_dict = torch.load(params.weight, map_location=device)
        gaze_detector.load_state_dict(state_dict)
        logging.info("Gaze Estimation model weights loaded.")
    except Exception as e:
        logging.info(f"Exception occured while loading pre-trained weights of gaze estimation model. Exception: {e}")

    gaze_detector.to(device)
    gaze_detector.eval()

    video_source = params.source
    if video_source.isdigit() or video_source == '0':
        cap = cv2.VideoCapture(int(video_source))
    else:
        cap = cv2.VideoCapture(video_source)

    if params.output:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(params.output, fourcc, cap.get(cv2.CAP_PROP_FPS), (width, height))

    if not cap.isOpened():
        raise IOError("Cannot open webcam")

    # Initialize posture analyzer
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    posture_analyzer = PostureAnalyzer(window_duration=4.0, fps=fps)

    with torch.no_grad():
        model = YOLO('yolo11n-pose.pt')
        i = 0
        while True:
            success, frame = cap.read()

            if not success:
                logging.info("Failed to obtain frame or EOF")
                break
            
            if i % posture_analyzer.skip == 0:
                results = model(frame)
                frame_ = results[0].plot()

                # Get pose keypoints and bounding box for the first person (if any)
                pose_keypoints = None
                person_bbox = None
                
                if len(results[0].keypoints.data) > 0:
                    pose_keypoints = results[0].keypoints.data[0].cpu().numpy()
                    
                    # Get bounding box for the first detected person
                    if len(results[0].boxes.data) > 0:
                        bbox_tensor = results[0].boxes.data[0]  # first person's bbox
                        person_bbox = bbox_tensor.cpu().numpy()[:4]  # x1, y1, x2, y2

                # Draw pose keypoints with confidence threshold
                if pose_keypoints is not None:
                    for j, keypoint in enumerate(pose_keypoints):
                        x, y, confidence = keypoint
                        if confidence > 0.7:
                            cv2.circle(frame_, (int(x), int(y)), 5, (0, 255, 0), -1)
                            cv2.putText(frame_, f'{j}', (int(x), int(y) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

                # Gaze estimation
                gaze_pitch, gaze_yaw = None, None
                bboxes, keypoints = face_detector.detect(frame)
                
                if len(bboxes) > 0 and len(keypoints) > 0:
                    # Use first detected face
                    bbox, keypoint = bboxes[0], keypoints[0]
                    x_min, y_min, x_max, y_max = map(int, bbox[:4])

                    image = frame[y_min:y_max, x_min:x_max]
                    try:
                        image = pre_process(image)
                    except Exception as e:
                        continue
                    image = image.to(device)

                    pitch, yaw = gaze_detector(image)

                    pitch_predicted, yaw_predicted = F.softmax(pitch, dim=1), F.softmax(yaw, dim=1)

                    # Mapping from binned to angles
                    pitch_predicted = torch.sum(pitch_predicted * idx_tensor, dim=1) * params.binwidth - params.angle
                    yaw_predicted = torch.sum(yaw_predicted * idx_tensor, dim=1) * params.binwidth - params.angle

                    # Degrees to Radians
                    gaze_pitch = np.radians(pitch_predicted.cpu()).item()
                    gaze_yaw = np.radians(yaw_predicted.cpu()).item()

                    # Draw box and gaze direction
                    draw_bbox_gaze(frame_, bbox, gaze_pitch, gaze_yaw)
                    cv2.putText(frame_, f'pitch: {gaze_pitch:.2f}, yaw: {gaze_yaw:.2f}', 
                            (x_min, y_max + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

                # Add data to posture analyzer and perform real-time analysis
                posture_analyzer.add_frame_and_analyze(pose_keypoints, gaze_pitch, gaze_yaw, person_bbox)
            else:
                frame_ = frame.copy()

            if params.output:
                out.write(frame_)

            if params.view:
                cv2.imshow('Demo', frame_)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            i += 1

    cap.release()
    if params.output:
        out.release()
    cv2.destroyAllWindows()
    
    # Finalize analysis and print comprehensive results
    posture_analyzer.finalize_analysis()
    posture_analyzer.print_final_statistics(save_json=True, json_filename=args.json_output)


if __name__ == "__main__":
    args = parse_args()

    if not args.view and not args.output:
        raise Exception("At least one of --view or --ouput must be provided.")

    main(args)