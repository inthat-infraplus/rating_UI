import os
import shutil


def extract_images(image_folder, txt_file, output_folder):
    # Create output folder if not exists
    os.makedirs(output_folder, exist_ok=True)

    # Read image names from txt file
    with open(txt_file, "r", encoding="utf-8") as file:
        image_names = [line.strip() for line in file if line.strip()]

    copied_count = 0
    missing_count = 0

    for image_name in image_names:
        source_path = os.path.join(image_folder, image_name)
        output_path = os.path.join(output_folder, image_name)

        if os.path.exists(source_path):
            shutil.copy2(source_path, output_path)
            copied_count += 1
            print(f"Copied: {image_name}")
        else:
            missing_count += 1
            print(f"Missing: {image_name}")

    print("\nFinished")
    print(f"Copied images: {copied_count}")
    print(f"Missing images: {missing_count}")
    print(f"Output folder: {output_folder}")


if __name__ == "__main__":
    image_folder = input("Enter path of image folder: ").strip()
    txt_file = input("Enter path of .txt file: ").strip()
    output_folder = input("Enter path to save output: ").strip()

    extract_images(image_folder, txt_file, output_folder)