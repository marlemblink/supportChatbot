
import streamlit as st
from dotenv import load_dotenv
from app_implementation import run_assistant

load_dotenv()

st.set_page_config(
    page_title="support Assistant AI the future",
    layout="centered"
)

st.title("Support Assistant AI the future")
st.caption(
    "support using RAG, claude, tools, MCP"
)

#chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous messages
for message in st.session_state.messages:

    with st.chat_message(message["role"]):
        st.markdown(message["content"])

#chat input
if prompt := st.chat_input("Ask your IT support question..."):

    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):

        with st.spinner("IT Assistant is thinking..."):

            try:
                history = st.session_state.messages[:-1]

                answer = run_assistant(
                    prompt,
                    history
                )

                st.markdown(answer)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer
                })

            except Exception as error:

                st.error(f"Error: {error}")