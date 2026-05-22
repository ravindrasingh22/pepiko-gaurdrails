from training.slm_classifier.data_pipeline import GL_COLUMN_NAMES, build_input_text


def main() -> None:
    sample = {
        "question": "Who is God?",
        "language": "en",
        "recent_context": "none",
    }
    print("SLM GL classifier inference scaffold.")
    print(build_input_text(sample))
    print(f"Expected classifier outputs: {', '.join(GL_COLUMN_NAMES)}")


if __name__ == "__main__":
    main()
