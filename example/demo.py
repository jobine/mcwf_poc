from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool
import os

zhipu_api_key = os.environ['ZHIPU_API_KEY']

llm = ChatOpenAI(
    model='glm-5',
    openai_api_base='https://open.bigmodel.cn/api/paas/v4',
    openai_api_key=zhipu_api_key,
    temperature=0.7,
    streaming=True
)


@tool
def search(query: str) -> str:
    '''Search the web for the query and return a summary of the results.'''
    return f'Search results for "{query}"'


tools = [search]
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: MessagesState) -> dict:
    return {
        'messages': [llm_with_tools.invoke(state['messages'])]
    }


graph = StateGraph(MessagesState)
graph.add_node('chatbot', chatbot)
graph.add_node('tools', ToolNode(tools))
graph.add_edge(START, 'chatbot')
graph.add_conditional_edges('chatbot', tools_condition)
graph.add_edge('tools', 'chatbot')

app = graph.compile()

# generate workflow image
img = app.get_graph().draw_mermaid_png()
with open('workflow.png', 'wb') as f:
    f.write(img)

result = app.invoke({
    'messages': [
        ('user', '你好，帮我搜索一下LangGraph的最新文档。')
    ]
})

print(result)