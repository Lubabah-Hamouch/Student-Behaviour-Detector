import cv2
import os
from pathlib import Path
import random


def extract_frames_smart(video_path, fps_target=1):
    """
    Extract frames and return them as a list with video metadata
    """
    cap = cv2.VideoCapture(video_path)
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(video_fps / fps_target)

    frame_count = 0
    frames_list = []
    video_name = Path(video_path).stem

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            frames_list.append({
                'frame': frame,
                'video_source': video_name,
                'frame_number': len(frames_list)
            })

        frame_count += 1

    cap.release()
    return frames_list


# Extract from all videos
videos = [
    "sleeping+variety.mp4",
    "concentrating.mp4",
    "handraising.mp4",
    "Handraise+tel.mp4",
    "telephone.mp4"
]

print("Extracting frames from all videos...")
all_frames = []
for video in videos:
    frames = extract_frames_smart(video, fps_target=1)
    all_frames.extend(frames)
    print(f"{video}: {len(frames)} frames")

print(f"\nTotal frames extracted: {len(all_frames)}")

# Shuffle frames randomly
random.shuffle(all_frames)
print("Frames shuffled randomly!")

# Save frames with sequential naming
output_folder = "raw_frames"
os.makedirs(output_folder, exist_ok=True)

# Create a mapping file for traceability
mapping_file = open(f"{output_folder}/frame_mapping.txt", "w")
mapping_file.write("image_name,source_video,original_frame_number\n")

for idx, frame_data in enumerate(all_frames, start=1):
    image_name = f"image{idx:03d}.jpg"
    cv2.imwrite(f"{output_folder}/{image_name}", frame_data['frame'])

    # Write mapping for traceability
    mapping_file.write(f"{image_name},{frame_data['video_source']},{frame_data['frame_number']}\n")

    if idx % 50 == 0:
        print(f"Saved {idx} images...")

mapping_file.close()
print(f"\n✓ All {len(all_frames)} frames saved to {output_folder}/")
print(f"✓ Mapping file saved to {output_folder}/frame_mapping.txt")