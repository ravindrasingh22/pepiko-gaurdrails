from training.slm_classifier.data_pipeline import GL_COLUMNS, build_input_text


def main() -> None:
    sample = {
        "question": "Who is God?",
        "age_band": "5-8",
        "language": "en",
        "recent_context": "none",
    }
    print("SLM GL classifier inference scaffold.")
    print(build_input_text(sample))
    print(f"Expected classifier outputs: {', '.join(GL_COLUMNS)}")


if __name__ == "__main__":
    main()
