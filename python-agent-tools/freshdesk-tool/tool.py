from dataiku.llm.agent_tools import BaseAgentTool
import requests
import logging
import base64
import json
import dataiku

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
                        "enum": ["create_ticket", "get_tickets", "close_ticket", "update_ticket_priority"],
                        "description": "The action to perform (create_ticket, get_tickets, close_ticket, or update_ticket_priority)"
                    },
                    "ticket_id": {
                        "type": "integer",
                        "description": "Ticket ID (required for get_tickets when search_by is 'id', close_ticket, or update_ticket_priority)"
                    },
                    "search_by": {
                        "type": "string",
                        "enum": ["id", "requester_email"],
                        "description": "Search criteria for get_tickets action (id or requester email)"
                    },
                    "requester_email": {
                        "type": "string",
                        "description": "Requester's email address (required when search_by is 'requester_email', close_ticket, or update_ticket_priority)"
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
            # Validate required fields
            required_fields = ["subject", "description", "requester_email", "name"]
            for field in required_fields:
                if field not in args:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate priority value
            if "priority" in args:
                if args["priority"] not in [1, 2, 3, 4]:
                    raise ValueError("Priority must be one of: 1 (Low), 2 (Medium), 3 (High), 4 (Urgent)")
                
            # Validate status if provided
            if "status" in args:
                if args["status"] not in [2, 3, 4, 5]:
                    raise ValueError("Status must be one of: 2 (Open), 3 (Pending), 4 (Resolved), 5 (Closed)")
            
            # Validate type if provided
            if "type" in args:
                if args["type"] not in self.ticket_types:
                    raise ValueError(f"Type must be one of: {', '.join(self.ticket_types)}")
            
            # Format ticket data according to Freshdesk API requirements
            ticket_data = {
                "subject": args["subject"],
                "description": args["description"],
                "email": args["requester_email"],
                "name": args["name"],
                "priority": args.get("priority", 1),
                "status": args.get("status", 2)  # Default to Open status
            }
            
            # Add optional fields if provided
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
            
        elif action == "get_tickets":
            if "search_by" not in args:
                raise ValueError("Missing required field: search_by")
                
            search_by = args["search_by"]
            
            if search_by == "id":
                if "ticket_id" not in args:
                    raise ValueError("Missing required field: ticket_id")
                if "requester_email" not in args:
                    raise ValueError("Missing required field: requester_email")
                    
                # Include requester details in the request
                result = self._make_request("GET", f"tickets/{args['ticket_id']}", params={"include": "requester"})
                
                # Verify that the provided email matches the ticket's requester email
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
                
            elif search_by == "requester_email":
                if "requester_email" not in args:
                    raise ValueError("Missing required field: requester_email")
                    
                # List all tickets filtered by requester email
                result = self._make_request("GET", "tickets", params={"email": args["requester_email"]})
                
                # Add URLs to each ticket
                for ticket in result:
                    ticket["url"] = f"https://{self.domain}/helpdesk/tickets/{ticket['id']}"
                
                # Create items for sources
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
                
            else:
                raise ValueError(f"Invalid search_by value: {search_by}")
            
        elif action == "close_ticket":
            # Validate required fields
            required_fields = ["ticket_id", "requester_email"]
            for field in required_fields:
                if field not in args:
                    raise ValueError(f"Missing required field: {field}")
            
            # First, get the ticket to verify the requester email
            ticket = self._make_request("GET", f"tickets/{args['ticket_id']}", params={"include": "requester"})
            
            # Verify that the provided email matches the ticket's requester email
            if ticket.get("requester", {}).get("email") != args["requester_email"]:
                raise ValueError("The provided requester email does not match the ticket's requester email")
            
            # Check if ticket is already closed
            if ticket.get("status") == 5:  # 5 = Closed
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
            
            # Update the ticket status to closed (5)
            update_data = {
                "status": 5  # 5 = Closed
            }
            
            result = self._make_request("PUT", f"tickets/{args['ticket_id']}", update_data)
            
            # Add a note to the ticket
            note_data = {
                "body": f"Ticket closed as requested by the original requester ({args['requester_email']})",
                "private": False  # Make the note visible to the requester
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
            
        elif action == "update_ticket_priority":
            # Validate required fields
            required_fields = ["ticket_id", "requester_email", "priority"]
            for field in required_fields:
                if field not in args:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate priority value
            if args["priority"] not in [1, 2, 3, 4]:
                raise ValueError("Priority must be one of: 1 (Low), 2 (Medium), 3 (High), 4 (Urgent)")
            
            # First, get the ticket to verify the requester email
            ticket = self._make_request("GET", f"tickets/{args['ticket_id']}", params={"include": "requester"})
            
            # Verify that the provided email matches the ticket's requester email
            if ticket.get("requester", {}).get("email") != args["requester_email"]:
                raise ValueError("The provided requester email does not match the ticket's requester email")
            
            # Check if priority is already at the requested level
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
            
            # Update the ticket priority
            update_data = {
                "priority": args["priority"]
            }
            
            result = self._make_request("PUT", f"tickets/{args['ticket_id']}", update_data)
            
            # Add a note to the ticket
            priority_levels = {
                1: "Low",
                2: "Medium",
                3: "High",
                4: "Urgent"
            }
            note_data = {
                "body": f"Ticket priority updated to {priority_levels[args['priority']]} as requested by the original requester ({args['requester_email']})",
                "private": False  # Make the note visible to the requester
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
            
        else:
            raise ValueError(f"Invalid action: {action}")