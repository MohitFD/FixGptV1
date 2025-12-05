import os
import shutil
import torch
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer

# ---------------------------------
# CONFIG
# ---------------------------------
BASE_DIR = "./new_model"        # yahan tumhare checkpoints pade hain
MERGED_DIR = "merged_phi3"       # output folder (auto create ho jayega)


def get_latest_checkpoint(folder: str) -> str:
    """
    new_model ke andar latest checkpoint-* folder return karega.
    Agar direct folder hi checkpoint ho to usko use karega.
    """
    checkpoints = []

    # case-1: inside folder checkpoint-* subdirs
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if (
            os.path.isdir(path)
            and name.startswith("checkpoint-")
            and os.path.exists(os.path.join(path, "adapter_config.json"))
        ):
            checkpoints.append(path)

    # case-2: BASE_DIR hi checkpoint ho
    if not checkpoints and os.path.exists(os.path.join(folder, "adapter_config.json")):
        return folder

    if not checkpoints:
        raise ValueError(f"❌ No LoRA checkpoints found in: {folder}")

    # sort by step number (checkpoint-1152, checkpoint-2000, ...)
    checkpoints.sort(key=lambda x: int(os.path.basename(x).split("-")[-1]))
    return checkpoints[-1]


def main():
    # -------------------------------
    # GPU CHECK
    # -------------------------------
    if not torch.cuda.is_available():
        raise RuntimeError("❌ CUDA GPU not available. 12GB GPU chahiye merge ke liye.")

    checkpoint_dir = get_latest_checkpoint(BASE_DIR)
    print(f"🔄 Using checkpoint: {checkpoint_dir}")

    os.makedirs(MERGED_DIR, exist_ok=True)

    # -------------------------------
    # LOAD PEFT MODEL (LoRA)
    # -------------------------------
    print("🔄 Loading LoRA + base model on GPU 0 (fp16)...")

    model = AutoPeftModelForCausalLM.from_pretrained(
        checkpoint_dir,
        torch_dtype=torch.float16,   # half precision -> VRAM kam
        device_map={"": 0},          # GPU 0
        low_cpu_mem_usage=True,
    )

    # -------------------------------
    # MERGE LoRA → BASE
    # -------------------------------
    print("🔄 Merging LoRA into base model (this may take a bit)...")
    merged_model = model.merge_and_unload()

    # -------------------------------
    # SAVE MERGED MODEL
    # -------------------------------
    print(f"💾 Saving merged model to: {MERGED_DIR}")

    merged_model.save_pretrained(
        MERGED_DIR,
        safe_serialization=True,     # safetensors
        max_shard_size="2GB",        # multiple shard files
    )

    # -------------------------------
    # SAVE TOKENIZER
    # -------------------------------
    print("🔄 Loading & saving tokenizer...")

    # tokenizer + special token files checkpoint se le lo
    tokenizer = AutoTokenizer.from_pretrained(checkpoint_dir)
    tokenizer.save_pretrained(MERGED_DIR)

    # extra useful files (optional but good)
    extra_files = [
        "chat_template.jinja",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "tokenizer.json",
    ]

    for fname in extra_files:
        src = os.path.join(checkpoint_dir, fname)
        dst = os.path.join(MERGED_DIR, fname)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy(src, dst)
            print(f"✔ Copied extra file: {fname}")

    print("\n🎉 Merge Completed Successfully!")
    print(f"📁 Final merged model folder: {os.path.abspath(MERGED_DIR)}")


if __name__ == "__main__":
    main()
