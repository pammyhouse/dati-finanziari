from transformers import GPTNeoForCausalLM, GPT2Tokenizer
import tensorflow as tf

# Scarica modello GPT-Neo 125M
model_name = "EleutherAI/gpt-neo-125M"
model = GPTNeoForCausalLM.from_pretrained(model_name)
tokenizer = GPT2Tokenizer.from_pretrained(model_name)

# Salva tokenizer localmente
tokenizer.save_pretrained("./model_tf/tokenizer")

# Converti in TensorFlow SavedModel
model.save_pretrained("./model_tf/tf_model", saved_model=True)

# Conversione in TFLite
converter = tf.lite.TFLiteConverter.from_saved_model("./model_tf/tf_model")
converter.optimizations = [tf.lite.Optimize.DEFAULT]
tflite_model = converter.convert()

# Salva modello TFLite
with open("./model_tf/gpt_neo_125.tflite", "wb") as f:
    f.write(tflite_model)

print("Conversione completata! File TFLite salvato in ./model_tf/gpt_neo_125.tflite")
