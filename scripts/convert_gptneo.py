from transformers import TFGPTNeoForCausalLM, GPT2Tokenizer
import tensorflow as tf

# Modello e tokenizer
model_name = "EleutherAI/gpt-neo-125M"

# Scarica tokenizer
tokenizer = GPT2Tokenizer.from_pretrained(model_name)
tokenizer.save_pretrained("./model_tf/tokenizer")

# Scarica modello TF da PyTorch
model = TFGPTNeoForCausalLM.from_pretrained(model_name, from_pt=True)

# Salva come TensorFlow SavedModel
model.save_pretrained("./model_tf/tf_model", saved_model=True)

# Conversione in TFLite con quantizzazione FP16
converter = tf.lite.TFLiteConverter.from_saved_model("./model_tf/tf_model")
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.target_spec.supported_types = [tf.float16]  # FP16

tflite_model = converter.convert()

# Salva modello TFLite
with open("./model_tf/gpt_neo_125_fp16.tflite", "wb") as f:
    f.write(tflite_model)

print("Conversione completata! File TFLite salvato in ./model_tf/gpt_neo_125_fp16.tflite")
