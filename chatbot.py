from rag_core import (
    answer_question,
    load_vector_store,
    make_client,
    print_sources,
    print_usage,
)


def main() -> None:
    print("Loading local vector database...")
    vector_store = load_vector_store()
    client = make_client()
    conversation_state = {}
    print("Ready. Type your question, or type 'exit' to quit.\n")

    while True:
        question = input("You: ").strip()
        if question.lower() in {"exit", "quit", "q"}:
            break
        if not question:
            continue

        answer, sources, usage = answer_question(
            question,
            vector_store,
            client,
            conversation_state=conversation_state,
        )
        print(f"\nBot: {answer}")
        print_sources(sources)
        print_usage(usage)
        print()


if __name__ == "__main__":
    main()
