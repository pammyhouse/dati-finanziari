# scripts/convert_gptneo.py

from transformers import TFGPTNeoForCausalLM, GPT2Tokenizer
import tensorflow as tf
import os

# Modello e tokenizer
model_name = "EleutherAI/gpt-neo-125M"

# Crea cartelle se non esistono
os.makedirs("./model_tf/tokenizer", exist_ok=True)
os.makedirs("./model_tf/tf_model", exist_ok=True)

print("Scaricando tokenizer...")
tokenizer = GPT2Tokenizer.from_pretrained(model_name)
tokenizer.save_pretrained("./model_tf/tokenizer")
print("Tokenizer salvato in ./model_tf/tokenizer")

print("Scaricando modello GPT-Neo 125M da PyTorch e convertendo in TensorFlow...")
model = TFGPTNeoForCausalLM.from_pretrained(model_name, from_pt=True)

print("Salvando modello come TensorFlow SavedModel...")
model.save_pretrained("./model_tf/tf_model", saved_model=True)
print("SavedModel salvato in ./model_tf/tf_model")

print("Convertendo in TFLite FP16...")
converter = tf.lite.TFLiteConverter.from_saved_model("./model_tf/tf_model")
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.target_spec.supported_types = [tf.float16]  # FP16

tflite_model = converter.convert()

# Salva modello TFLite
tflite_path = "./model_tf/gpt_neo_125_fp16.tflite"
with open(tflite_path, "wb") as f:
    f.write(tflite_model)

print(f"Conversione completata! File TFLite salvato in {tflite_path}")
