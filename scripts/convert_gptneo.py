# scripts/convert_gptneo_onnx.py

import torch
from transformers import GPTNeoForCausalLM, GPT2Tokenizer
import os

model_name = "EleutherAI/gpt-neo-125M"

# Crea cartelle
os.makedirs("./model_onnx", exist_ok=True)
os.makedirs("./model_onnx/tokenizer", exist_ok=True)

print("Scaricando tokenizer...")
tokenizer = GPT2Tokenizer.from_pretrained(model_name)
tokenizer.save_pretrained("./model_onnx/tokenizer")
print("Tokenizer salvato in ./model_onnx/tokenizer")

print("Scaricando modello GPT-Neo 125M...")
model = GPTNeoForCausalLM.from_pretrained(model_name)
model.eval()

# Dummy input per esportazione
dummy_input = tokenizer("Hello world", return_tensors="pt")
input_ids = dummy_input["input_ids"]

# Esporta in ONNX
onnx_path = "./model_onnx/gpt_neo_125.onnx"
print("Esportando modello in ONNX...")
torch.onnx.export(
    model,
    (input_ids,),
    onnx_path,
    input_names=["input_ids"],
    output_names=["logits"],
    opset_version=13,
    do_constant_folding=True,
    dynamic_axes={"input_ids": {0: "batch_size", 1: "seq_len"},
                  "logits": {0: "batch_size", 1: "seq_len"}}
)

print(f"Conversione completata! File ONNX salvato in {onnx_path}")
