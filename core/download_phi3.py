from huggingface_hub import snapshot_download

print("⏳ Downloading Phi-3 Mini...")

snapshot_download(
    repo_id="microsoft/Phi-3-mini-4k-instruct",
    local_dir="merged_phi3",
    ignore_patterns=["*.md", "*.png"]
)

print("✅ Download complete! Model saved in merged_phi3/")
