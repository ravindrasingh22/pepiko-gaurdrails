from training.slm_classifier.data_pipeline import FLAG_VOCAB, G1_VOCAB, G2_VOCAB, build_input_text


def main() -> None:
    sample = {
        "question": "Who is God?",
        "language": "en",
        "recent_context": "none",
    }
    print("SLM G1/G2/flag classifier inference scaffold.")
    print(build_input_text(sample))
    print(f"G1 outputs: {', '.join(G1_VOCAB)}")
    print(f"G2 outputs: {', '.join(G2_VOCAB)}")
    print(f"Flag outputs: {', '.join(FLAG_VOCAB)}")


if __name__ == "__main__":
    main()
