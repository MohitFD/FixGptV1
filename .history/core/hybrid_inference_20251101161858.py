import sys
from bert_inference import predict_intent
from falcon_inference import FixHRModelInference

# Initialize Falcon model
falcon = FixHRModelInference()
falcon.load_model()

def hybrid_response(user_input):
    """Combine BERT + Falcon for contextual intelligent responses"""
    # Step 1: Predict intent using BERT
    intent = predict_intent(user_input)

    # Step 2: Create a meaningful prompt for Falcon
    prompt = f"""
    The detected intent is: {intent}.
    User said: "{user_input}".
    Based on this intent, generate a polite, short, and professional response
    that fits FixHR HR system context.
    """

    # Step 3: Generate Falcon response
    response = falcon.generate_response(prompt)
    return intent, response


if __name__ == "__main__":
    print("\n🤖 FixHR Hybrid AI Model (BERT + Falcon)")
    print("Type your query (or 'exit' to quit)\n")

    while True:
        user_input = input(">> ").strip()
        if user_input.lower() == "exit":
            print("👋 Exiting hybrid model tester...")
            break

        intent, reply = hybrid_response(user_input)
        print(f"\n🧭 Intent: {intent}")
        print(f"💬 Falcon Response: {reply}\n")
        sys.stdout.flush()
