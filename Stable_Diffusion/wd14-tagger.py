import sys
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

import numpy as np
import pandas as pd
import timm
import torch
from huggingface_hub import hf_hub_download
from huggingface_hub.utils import HfHubHTTPError
from PIL import Image
from simple_parsing import field, parse_known_args
from timm.data import create_transform, resolve_data_config
from torch import Tensor, nn
from torch.nn import functional as F

torch_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL_REPO_MAP = {
    "vit": "SmilingWolf/wd-vit-tagger-v3",
    "swinv2": "SmilingWolf/wd-swinv2-tagger-v3",
    "convnext": "SmilingWolf/wd-convnext-tagger-v3",
}


def pil_ensure_rgb(image: Image.Image) -> Image.Image:
    # convert to RGB/RGBA if not already (deals with palette images etc.)
    if image.mode not in ["RGB", "RGBA"]:
        image = image.convert("RGBA") if "transparency" in image.info else image.convert("RGB")
    # convert RGBA to RGB with white background
    if image.mode == "RGBA":
        canvas = Image.new("RGBA", image.size, (255, 255, 255))
        canvas.alpha_composite(image)
        image = canvas.convert("RGB")
    return image


def pil_pad_square(image: Image.Image) -> Image.Image:
    w, h = image.size
    # get the largest dimension so we can pad to a square
    px = max(image.size)
    # pad to square with white background
    canvas = Image.new("RGB", (px, px), (255, 255, 255))
    canvas.paste(image, ((px - w) // 2, (px - h) // 2))
    return canvas


@dataclass
class LabelData:
    names: list[str]
    rating: list[np.int64]
    general: list[np.int64]
    character: list[np.int64]


def load_labels_hf(
    repo_id: str,
    revision: Optional[str] = None,
    token: Optional[str] = None,
) -> LabelData:
    try:
        csv_path = hf_hub_download(
            repo_id=repo_id, filename="selected_tags.csv", revision=revision, token=token
        )
        csv_path = Path(csv_path).resolve()
    except HfHubHTTPError as e:
        raise FileNotFoundError(f"selected_tags.csv failed to download from {repo_id}") from e

    df: pd.DataFrame = pd.read_csv(csv_path, usecols=["name", "category"])
    tag_data = LabelData(
        names=df["name"].tolist(),
        rating=list(np.where(df["category"] == 9)[0]),
        general=list(np.where(df["category"] == 0)[0]),
        character=list(np.where(df["category"] == 4)[0]),
    )

    return tag_data


def get_tags(
    probs: Tensor,
    labels: LabelData,
    gen_threshold: float,
    char_threshold: float,
):
    # Convert indices+probs to labels
    probs = list(zip(labels.names, probs.numpy()))

    # First 4 labels are actually ratings
    rating_labels = dict([probs[i] for i in labels.rating])

    # General labels, pick any where prediction confidence > threshold
    gen_labels = [probs[i] for i in labels.general]
    gen_labels = [x for x in gen_labels if x[1] >= gen_threshold]
    gen_labels = sorted(gen_labels, key=lambda item: item[1], reverse=True)[:100]
    gen_labels = dict(gen_labels)

    # Character labels, pick any where prediction confidence > threshold
    char_labels = [probs[i] for i in labels.character]
    char_labels = dict([x for x in char_labels if x[1] > char_threshold])
    char_labels = dict(sorted(char_labels.items(), key=lambda item: item[1], reverse=True))

    # Combine general and character labels, sort by confidence
    combined_names = [x for x in gen_labels]
    combined_names.extend([x for x in char_labels])

    # Convert to a string suitable for use as a training caption
    caption = ", ".join(combined_names)
    taglist = caption.replace("_", " ").replace("(", "\(").replace(")", "\)")

    return caption, taglist, rating_labels, char_labels, gen_labels

@dataclass
class ScriptOptions:
    image_files: Optional[List[Path]] = field(default=None, help="Path to one or more image files")
    model: str = field(default="vit", help="Name of the model to use for tagging")
    gen_threshold: float = field(default=0.09, help="Threshold for general tags")
    char_threshold: float = field(default=0.0009, help="Threshold for character tags")
    output_file: Optional[Path] = field(default=None, help="Path to the output text file")

def main(opts: ScriptOptions):
    repo_id = MODEL_REPO_MAP.get(opts.model)
    print(f"Loading model '{opts.model}' from '{repo_id}'...")
    model: nn.Module = timm.create_model("hf-hub:" + repo_id).eval()
    state_dict = timm.models.load_state_dict_from_hf(repo_id)
    model.load_state_dict(state_dict)
    if torch_device.type != "cpu":
        model = model.to(torch_device)

    print("Loading tag list...")
    labels: LabelData = load_labels_hf(repo_id=repo_id)

    print("Creating data transform...")
    transform = create_transform(**resolve_data_config(model.pretrained_cfg, model=model))

    if not opts.image_files:
        print("No image files provided.")
        return

    output_filename = f"hasil_tag_{os.path.splitext(Path(sys.argv[0]).name)[0]}.txt"
    if opts.output_file:
        output_filename = opts.output_file

    all_results = {}
    for image_path in opts.image_files:
        if not image_path.is_file():
            print(f"Warning: Image file not found: {image_path}")
            continue

        print(f"\nProcessing image: {image_path}")
        img_input: Image.Image = Image.open(image_path)
        img_input = pil_ensure_rgb(img_input)
        img_input = pil_pad_square(img_input)
        inputs: Tensor = transform(img_input).unsqueeze(0)
        inputs = inputs[:, [2, 1, 0]]

        with torch.inference_mode():
            if torch_device.type != "cpu":
                inputs = inputs.to(torch_device)
            outputs = model.forward(inputs)
            outputs = F.sigmoid(outputs)
            outputs = outputs.to("cpu")

        caption, taglist, ratings, character, general = get_tags(
            probs=outputs.squeeze(0),
            labels=labels,
            gen_threshold=opts.gen_threshold,
            char_threshold=opts.char_threshold,
        )
        all_results[image_path.name] = {
            "caption": caption,
            "tags": taglist,
            "ratings": ratings,
            "character": character,
            "general": general,
        }

    try:
        mode = "a" if Path(output_filename).is_file() else "w"
        with open(output_filename, mode) as f:
            for filename, res in all_results.items():
                f.write(f"Image: {filename}\n")
                f.write(f"Caption: {res['caption']}\n")
                f.write(f"Tags: {res['tags']}\n")
                f.write("\nRatings:\n")
                for k, v in res['ratings'].items():
                    f.write(f"  {k}: {v:.3f}\n")
                f.write("\nCharacter tags:\n")
                for k, v in res['character'].items():
                    f.write(f"  {k}: {v:.3f}\n")
                f.write("\nGeneral tags:\n")
                for k, v in res['general'].items():
                    f.write(f"  {k}: {v:.3f}\n")
                f.write("-" * 40 + "\n\n")
        print(f"\nResults for all images written to: {output_filename}")
    except Exception as e:
        print(f"Error writing to output file: {e}")
    print("--------")
    print(f"Caption: {caption}")
    print("--------")
    print(f"Tags: {taglist}")

    print("--------")
    print("Ratings:")
    for k, v in ratings.items():
        print(f"  {k}: {v:.3f}")

    print("--------")
    print(f"Character tags (threshold={opts.char_threshold}):")
    for k, v in character.items():
        print(f"  {k}: {v:.3f}")

    print("--------")
    print(f"General tags (threshold={opts.gen_threshold}):")
    for k, v in general.items():
        print(f"  {k}: {v:.3f}")

    print("Done!")

if __name__ == "__main__":
    opts = parse_known_args(ScriptOptions)[0]
    if opts.model not in MODEL_REPO_MAP:
        print(f"Available models: {list(MODEL_REPO_MAP.keys())}")
        raise ValueError(f"Unknown model name '{opts.model}'")
    main(opts)
