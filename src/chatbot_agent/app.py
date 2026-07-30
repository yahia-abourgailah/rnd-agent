from graph import graph


while True:
    question = input("You: ")

    if question.lower() == "exit":
        break

    result = graph.invoke(
        {
            "messages": [question]
        }
    )

    print("Bot:", result["messages"][-1].content)