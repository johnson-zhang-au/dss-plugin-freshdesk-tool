from dataiku.llm.agent_tools import BaseAgentTool
import requests
import logging
import base64
import json

class FreshdeskTool(BaseAgentTool):
    def set_config(self, config, plugin_config):
        self.config = config
        self.api_key = self.config["freshdesk_api_connection"]["apiKey"]
        self.domain = self.config["freshdesk_api_connection"]["freshdesk_domain"]
        self.ticket_types = self.config["freshdesk_api_connection"]["ticket_types"]
        self.base_url = f"https://{self.domain}/api/v2"

    def get_descriptor(self, tool):
        return {
            "description": "Interacts with Freshdesk to create, retrieve, close, and update support tickets",
            "inputSchema": {
                "$id": "https://dataiku.com/agents/tools/freshdesk/input",
                "title": "Input for the Freshdesk tool",
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create_ticket", "get_ticket_by_id", "get_tickets_by_email", "close_ticket", "update_ticket_priority"],
                        "description": "The action to perform (create_ticket, get_ticket_by_id, get_tickets_by_email, close_ticket, or update_ticket_priority)"
                    },
                    "ticket_id": {
                        "type": "integer",
                        "description": "Ticket ID (required for get_ticket_by_id, close_ticket, or update_ticket_priority)"
                    },
                    "requester_email": {
                        "type": "string",
                        "description": "Requester's email address (required for get_ticket_by_id, get_tickets_by_email, close_ticket, or update_ticket_priority)"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Ticket subject (required for create_ticket action)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Ticket description (required for create_ticket action)"
                    },
                    "name": {
                        "type": "string",
                        "description": "Name of the requester (required for create_ticket action)"
                    },
                    "type": {
                        "type": "string",
                        "enum": self.ticket_types,
                        "description": f"Ticket type (must be one of: {', '.join(self.ticket_types)}) (required for create_ticket action)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of tags to apply to the ticket"
                    },
                    "priority": {
                        "type": "integer",
                        "enum": [1, 2, 3, 4],
                        "description": "Ticket priority (1=Low, 2=Medium, 3=High, 4=Urgent) (required for update_ticket_priority action)"
                    },
                    "status": {
                        "type": "integer",
                        "enum": [2, 3, 4, 5],
                        "description": "Ticket status (2=Open, 3=Pending, 4=Resolved, 5=Closed)"
                    }
                },
                "required": ["action"]
            }
        }

    def _make_request(self, method, endpoint, data=None, params=None):
        # Create base64 encoded API key
        auth_string = f"{self.api_key}:X"  # Freshdesk requires ':X' suffix
        auth_bytes = auth_string.encode('ascii')
        base64_bytes = base64.b64encode(auth_bytes)
        base64_auth = base64_bytes.decode('ascii')
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {base64_auth}"
        }
        url = f"{self.base_url}/{endpoint}"
        
        try:
            # Log the request details for debugging
            logging.info(f"Making {method} request to {url}")
            if data:
                logging.info(f"Request data: {json.dumps(data, indent=2)}")
            if params:
                logging.info(f"Request params: {params}")
            
            response = requests.request(method, url, headers=headers, json=data, params=params)
            
            # Log response details for debugging
            logging.info(f"Response status code: {response.status_code}")
            logging.info(f"Response headers: {dict(response.headers)}")
            logging.info(f"Response body: {response.text}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Freshdesk API error: {str(e)}")
            if hasattr(e.response, 'text'):
                logging.error(f"Error response: {e.response.text}")
            raise

    def invoke(self, input, trace):
        args = input["input"]
        action = args["action"]

        if action == "create_ticket":
            return self._create_ticket(args)
        elif action == "get_ticket_by_id":
            return self._get_ticket_by_id(args)
        elif action == "get_tickets_by_email":
            return self._get_tickets_by_email(args)
        elif action == "close_ticket":
            return self._close_ticket(args)
        elif action == "update_ticket_priority":
            return self._update_ticket_priority(args)
        else:
            raise ValueError(f"Invalid action: {action}")

    def _create_ticket(self, args):
        # Validate required fields
        required_fields = ["subject", "description", "requester_email", "name"]
        for field in required_fields:
            if field not in args:
                raise ValueError(f"Missing required field: {field}")

        # Validate priority value
        if "priority" in args and args["priority"] not in [1, 2, 3, 4]:
            raise ValueError("Priority must be one of: 1 (Low), 2 (Medium), 3 (High), 4 (Urgent)")

        # Validate status if provided
        if "status" in args and args["status"] not in [2, 3, 4, 5]:
            raise ValueError("Status must be one of: 2 (Open), 3 (Pending), 4 (Resolved), 5 (Closed)")

        # Validate type if provided
        if "type" in args and args["type"] not in self.ticket_types:
            raise ValueError(f"Type must be one of: {', '.join(self.ticket_types)}")

        # Format ticket data
        ticket_data = {
            "subject": args["subject"],
            "description": args["description"],
            "email": args["requester_email"],
            "name": args["name"],
            "priority": args.get("priority", 1),
            "status": args.get("status", 2)
        }
        if "type" in args:
            ticket_data["type"] = args["type"]
        if "tags" in args:
            ticket_data["tags"] = args["tags"]

        result = self._make_request("POST", "tickets", ticket_data)
        return {
            "output": {
                "message": "Ticket created successfully",
                "ticket_id": result["id"],
                "url": f"https://{self.domain}/helpdesk/tickets/{result['id']}",
                "ticket": result
            },
            "sources": [{
                "toolCallDescription": f"Created Freshdesk ticket with subject: {args['subject']}",
                "items": [{
                    "type": "SIMPLE_DOCUMENT",
                    "title": f"Ticket #{result['id']}",
                    "url": f"https://{self.domain}/helpdesk/tickets/{result['id']}"
                }]
            }]
        }

    def _get_ticket_by_id(self, args):
        required_fields = ["ticket_id", "requester_email"]
        for field in required_fields:
            if field not in args:
                raise ValueError(f"Missing required field: {field}")
                    
        result = self._make_request("GET", f"tickets/{args['ticket_id']}", params={"include": "requester"})
        
        if result.get("requester", {}).get("email") != args["requester_email"]:
            raise ValueError("The provided requester email does not match the ticket's requester email")
        
        return {
            "output": {
                "message": "Ticket retrieved successfully",
                "ticket_id": result["id"],
                "url": f"https://{self.domain}/helpdesk/tickets/{result['id']}",
                "ticket": result
            },
            "sources": [{
                "toolCallDescription": f"Retrieved Freshdesk ticket #{args['ticket_id']}",
                "items": [{
                    "type": "SIMPLE_DOCUMENT",
                    "title": f"Ticket #{result['id']}",
                    "url": f"https://{self.domain}/helpdesk/tickets/{result['id']}"
                }]
            }]
        }

    def _get_tickets_by_email(self, args):
        if "requester_email" not in args:
            raise ValueError("Missing required field: requester_email")
                
        result = self._make_request("GET", "tickets", params={"email": args["requester_email"]})
        
        for ticket in result:
            ticket["url"] = f"https://{self.domain}/helpdesk/tickets/{ticket['id']}"
        
        items = []
        for ticket in result:
            items.append({
                "type": "SIMPLE_DOCUMENT",
                "title": f"Ticket #{ticket['id']}",
                "url": f"https://{self.domain}/helpdesk/tickets/{ticket['id']}"
            })
        
        return {
            "output": {
                "message": f"Found {len(result)} tickets for requester {args['requester_email']}",
                "tickets": result
            },
            "sources": [{
                "toolCallDescription": f"Retrieved Freshdesk tickets for requester: {args['requester_email']}",
                "items": items
            }]
        }

    def _close_ticket(self, args):
        required_fields = ["ticket_id", "requester_email"]
        for field in required_fields:
            if field not in args:
                raise ValueError(f"Missing required field: {field}")
        
        ticket = self._make_request("GET", f"tickets/{args['ticket_id']}", params={"include": "requester"})
        
        if ticket.get("requester", {}).get("email") != args["requester_email"]:
            raise ValueError("The provided requester email does not match the ticket's requester email")
        
        if ticket.get("status") == 5:
            return {
                "output": {
                    "message": "Ticket is already closed",
                    "ticket_id": ticket["id"],
                    "url": f"https://{self.domain}/helpdesk/tickets/{ticket['id']}",
                    "ticket": ticket
                },
                "sources": [{
                    "toolCallDescription": f"Checked status of Freshdesk ticket #{args['ticket_id']}",
                    "items": [{
                        "type": "SIMPLE_DOCUMENT",
                        "title": f"Ticket #{ticket['id']}",
                        "url": f"https://{self.domain}/helpdesk/tickets/{ticket['id']}"
                    }]
                }]
            }
        
        update_data = {
            "status": 5
        }
        
        result = self._make_request("PUT", f"tickets/{args['ticket_id']}", update_data)
        
        note_data = {
            "body": f"Ticket closed as requested by the original requester ({args['requester_email']})",
            "private": False
        }
        self._make_request("POST", f"tickets/{args['ticket_id']}/notes", note_data)
        
        return {
            "output": {
                "message": "Ticket closed successfully",
                "ticket_id": result["id"],
                "url": f"https://{self.domain}/helpdesk/tickets/{result['id']}",
                "ticket": result
            },
            "sources": [{
                "toolCallDescription": f"Closed Freshdesk ticket #{args['ticket_id']}",
                "items": [{
                    "type": "SIMPLE_DOCUMENT",
                    "title": f"Ticket #{result['id']}",
                    "url": f"https://{self.domain}/helpdesk/tickets/{result['id']}"
                }]
            }]
        }

    def _update_ticket_priority(self, args):
        required_fields = ["ticket_id", "requester_email", "priority"]
        for field in required_fields:
            if field not in args:
                raise ValueError(f"Missing required field: {field}")
        
        if args["priority"] not in [1, 2, 3, 4]:
            raise ValueError("Priority must be one of: 1 (Low), 2 (Medium), 3 (High), 4 (Urgent)")
        
        ticket = self._make_request("GET", f"tickets/{args['ticket_id']}", params={"include": "requester"})
        
        if ticket.get("requester", {}).get("email") != args["requester_email"]:
            raise ValueError("The provided requester email does not match the ticket's requester email")
        
        if ticket.get("priority") == args["priority"]:
            return {
                "output": {
                    "message": "Ticket priority is already at the requested level",
                    "ticket_id": ticket["id"],
                    "url": f"https://{self.domain}/helpdesk/tickets/{ticket['id']}",
                    "ticket": ticket
                },
                "sources": [{
                    "toolCallDescription": f"Checked priority of Freshdesk ticket #{args['ticket_id']}",
                    "items": [{
                        "type": "SIMPLE_DOCUMENT",
                        "title": f"Ticket #{ticket['id']}",
                        "url": f"https://{self.domain}/helpdesk/tickets/{ticket['id']}"
                    }]
                }]
            }
        
        update_data = {
            "priority": args["priority"]
        }
        
        result = self._make_request("PUT", f"tickets/{args['ticket_id']}", update_data)
        
        priority_levels = {
            1: "Low",
            2: "Medium",
            3: "High",
            4: "Urgent"
        }
        note_data = {
            "body": f"Ticket priority updated to {priority_levels[args['priority']]} as requested by the original requester ({args['requester_email']})",
            "private": False
        }
        self._make_request("POST", f"tickets/{args['ticket_id']}/notes", note_data)
        
        return {
            "output": {
                "message": "Ticket priority updated successfully",
                "ticket_id": result["id"],
                "url": f"https://{self.domain}/helpdesk/tickets/{result['id']}",
                "ticket": result
            },
            "sources": [{
                "toolCallDescription": f"Updated priority of Freshdesk ticket #{args['ticket_id']} to {args['priority']}",
                "items": [{
                    "type": "SIMPLE_DOCUMENT",
                    "title": f"Ticket #{result['id']}",
                    "url": f"https://{self.domain}/helpdesk/tickets/{result['id']}"
                }]
            }]
        }