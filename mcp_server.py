
from mcp.server import MCPServer
from threading import Lock
import asyncio
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

# MCP Server
mcp = MCPServer(
    name="IT Helpdesk MCP Server",
    version="1.0.0"
)

ticket_lock = Lock()


# In-memory ticket database
tickets = {
    "IT-101": {
        "ticket_id": "IT-101",
        "employee": "Rahul",
        "issue": "Laptop running slowly",
        "description": "System takes too long to start",
        "priority": "Medium",
        "status": "Open"
    },
    "IT-102": {
        "ticket_id": "IT-102",
        "employee": "Priya",
        "issue": "VPN not connecting",
        "description": "Unable to connect to office VPN",
        "priority": "High",
        "status": "In Progress"
    },
    "IT-103": {
        "ticket_id": "IT-103",
        "employee": "Arun",
        "issue": "Printer not working",
        "description": "Printer is not detected by laptop",
        "priority": "Low",
        "status": "Resolved"
    }
}


# Create support ticket
@mcp.tool()
def create_support_ticket(
    employee: str,
    issue: str,
    description: str,
    priority: str = "Medium"
) -> dict:
    """
    Create a new IT support ticket.

    Args:
        employee: Employee name.
        issue: Short description of the issue.
        description: Detailed problem description.
        priority: Low, Medium, High or Critical.
    """

    employee = employee.strip()
    issue = issue.strip()
    description = description.strip()
    priority = priority.strip().capitalize()

    if not employee or not issue or not description:
        return {
            "error": "Employee, issue and description are required."
        }

    if priority not in ["Low", "Medium", "High", "Critical"]:
        return {"error": "Invalid priority."}

    with ticket_lock:

        existing_numbers = [
            int(ticket_id.split("-")[1])
            for ticket_id in tickets
            if ticket_id.startswith("IT-")
            and ticket_id.split("-")[1].isdigit()
        ]

        next_number = max(existing_numbers, default=100) + 1

        ticket_id = f"IT-{next_number:03d}"

        new_ticket = {
            "ticket_id": ticket_id,
            "employee": employee,
            "issue": issue,
            "description": description,
            "priority": priority,
            "status": "Open"
        }

        tickets[ticket_id] = new_ticket

    return {
        "message": "Support ticket created successfully",
        "ticket": new_ticket
    }


# Check ticket status
@mcp.tool()
def check_ticket_status(ticket_id: str) -> dict:
    """
    Check the status of an existing IT support ticket.

    Args:
        ticket_id: Ticket ID, for example IT-101.
    """

    ticket_id = ticket_id.strip().upper()

    if not ticket_id:
        return {"error": "Ticket ID is required."}

    with ticket_lock:

        ticket = tickets.get(ticket_id)

        if ticket is None:
            return {
                "error": f"Ticket {ticket_id} was not found."
            }

        return ticket.copy()


# Run MCP server

# Create Streamable HTTP application
mcp_app = mcp.streamable_http_app()


# Manage MCP server lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):

    async with mcp_app.router.lifespan_context(mcp_app):
        yield


# FastAPI application
app = FastAPI(lifespan=lifespan)

app.mount("/", mcp_app)


# Run server
if __name__ == "__main__":

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=3000
    )

    server = uvicorn.Server(config)

    loop_factory = (
        asyncio.SelectorEventLoop
        if sys.platform == "win32"
        else None
    )

    print("MCP server running at http://localhost:3000")

    asyncio.run(
        server.serve(),
        loop_factory=loop_factory
    )
