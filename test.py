import torch, transformers
print("CUDA available:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None")
print("PyTorch:", torch.__version__)
print("Transformers:", transformers.__version__)

