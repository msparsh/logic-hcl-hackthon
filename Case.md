# Autonomous Customer Support
An autonomous AI agent system that turns messy customer chat messages into safe, verified database actions. By combining AI reasoning with strict code-based guardrails, the engine allows customers to easily manage complex order changes—like updating shipping addresses, canceling orders, or postponing deliveries without risking AI hallucinations, double-booking, or accidental database errors.
Core Architecture & System Workflow: 
1.	Ingest & Identify: The system takes in the customer's chat message and instantly looks up their profile in the database to verify their identity and pull up their account history.
2.	Parse Intent: An AI agent reads the unstructured text to figure out exactly what the customer wants to do (e.g., change an address) and extracts the key details needed (like the new street name or order number).
3.	Verify Guardrails: Before making any changes, the system runs the request through a strict, code-governed checkpoint to check business rules (e.g., "Is the item already shipped?" or "Did the payment fail?"). If a rule is broken, the change is blocked.
4.	Update Database: Once approved, the system safely writes the new data directly to the database in an isolated transaction to prevent conflicts. It logs the change and prompts the AI to send a clear, friendly confirmation back to the user.
Source: https://www.kaggle.com/datasets/bytadit/transactional-ecommerce/data 

PS: Any source can be used as the reference source is provided for clarity

2.  Tech Stack Options (Not limited to)
•	Programming: Python
•	Core Libraries: Transformers, LangChain, LlamaIndex, CrewAI, OpenAI API, Pandas, NumPy, Pydantic, Ragas, deepeval.
•	Gen AI Capabilities: Prompt Engineering, Embeddings, Vector DBs (FAISS, Chroma, Pinecone).
•	Deployment: Streamlit (UI), Flask / FastAPI (API), LLM API Integration.
•	Databases: SQL Server DB, Postgres DB
