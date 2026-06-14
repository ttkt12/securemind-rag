from answer_engine import answer_chat
from rag_core import load_vector_store, make_client, print_sources, print_usage
from memory import make_memory


def main() -> None:
    print("Loading local vector database...")
    vector_store = load_vector_store()
    client = make_client()
    memory = make_memory()
    conversation_state = {}
    print(memory.status_message())
    print("Ready. Type your question, or type 'exit' to quit.\n")

    while True:
        question = input("You: ").strip()
        if question.lower() in {"exit", "quit", "q"}:
            break
        if not question:
            continue

        memory_context = memory.recall(question)
        result = answer_chat(
            question,
            vector_store,
            client,
            conversation_state=conversation_state,
            memory_context=memory_context,
        )
        answer = result.get("answer", "")
        sources = result.get("sources", [])
        usage = result.get("usage")
        memory.remember(question, answer)
        print(f"\nBot: {answer}")
        print_sources(sources)
        print_usage(usage)
        print()


if __name__ == "__main__":
    main()
