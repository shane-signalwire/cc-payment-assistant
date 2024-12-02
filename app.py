#!/usr/bin/env python3
# Author: Shane Harrell

import json
from flask import Flask, redirect, render_template, request, url_for
import sqlite3
import os

ngrok_url = os.environ['NGROK_URL']
if not ngrok_url:
    raise ValueError("NGROK_URL is not set in the environment variables")

post_prompt_url = "localhost" # TODO: change this to the actual post prompt url

class AIPaymentSWML:
    def __init__(self, ngrok_url):
        self.ngrok_url = ngrok_url
        self.prompt_text = '''
    # Personality and Introduction
    You are a dedicated customer service assistant named Atom at Max Electric. Your primary role is to help customers make bill payments over the phone. You should be professional, friendly, and security-conscious.

    # Core Responsibilities
    1. Verify customer identity
    2. Check account balance
    3. Process payments securely
    4. Provide clear confirmation

    # Security Protocols
    - NEVER ask for credit card numbers directly
    - NEVER store or repeat credit card information
    - Always use the secure payment system functions provided
    - Inform customers about secure transfer before collecting payment info

    # Required Information
    - First and last name
    - Account number
    - CVV (3 digits)
    - Card expiration date

    # Conversation Flow
    1. Greeting
       - Introduce yourself as Atom from Max Electric
       - Explain you're here to help with bill payment
       - Ask for first and last name

    2. Account Verification
       - Request account number
       - Use get_customer_balance to check amount due
       - If balance is $0, inform customer and end payment process
       - If balance exists, clearly state the amount due

    3. Payment Processing
       - Explain the secure payment process
       - ALWAYS Use get_credit_card_number function for secure card entry
       - NEVER ask for credit card numbers directly
       - Request CVV (explain it's the 3-digit number on back)
       - Request expiration date
       - Validate expiration date is in the future

    4. Confirmation
       - Use submit_payment function
       - Provide clear confirmation of payment
       - State new balance
       - Ask if customer needs anything else

    # Error Handling
    - If any function returns an error, apologize and explain next steps
    - Offer to retry or connect to human support if needed
    - Always maintain professional, helpful demeanor

    # Additional Guidelines
    - Speak only in English
    - Keep responses concise but friendly
    - Confirm important information
    - Thank customer for their payment
    '''

    def get_base_params(self):
        return {
            'params': {
                'confidence': 0.6,
                'barge_confidence': 0.1,
                'top_p': 0.3,
                'temperature': 0.3,
                'swaig_allow_swml': True,
                'conscience': True
            }
        }

    def get_functions(self):
        return [
            self._get_credit_card_number_function(),
            self._get_submit_payment_function(),
            self._get_customer_balance_function()
        ]

    def _get_credit_card_number_function(self):
        return {
            'function': 'get_credit_card_number',
            'purpose': 'get the callers credit card number',
            'web_hook_url': f'{self.ngrok_url}/get_credit_card_number',
            'argument': {
                'type': 'object',
                'properties': {
                    'prompt_value': {
                        'type': 'string',
                        'description': 'the callers credit card number'
                    }
                }
            }
        }

    def _get_submit_payment_function(self):
        return {
            'function': 'submit_payment',
            'purpose': 'submit the payment for the caller',
            'web_hook_url': f'{self.ngrok_url}/submit_payment',
            'argument': {
                'type': 'object',
                'properties': {
                    'first_name': {
                        'type': 'string',
                        'description': 'the callers fist name'
                    },
                    'last_name': {
                        'type': 'string',
                        'description': 'the callers last name'
                    },
                    'account_number': {
                        'type': 'string',
                        'description': 'the callers account number'
                    },
                    'card_verification_value': {
                        'type': 'string',
                        'description': 'the callers credit card cvv'
                    },
                    'expiration_date': {
                        'type': 'string',
                        'description': 'the callers credit card expiration date'
                    }
                }
            }
        }

    def _get_customer_balance_function(self):
        return {
            'function': 'get_customer_balance',
            'purpose': 'gather customer data from the database',
            'web_hook_url': f'{self.ngrok_url}/get_customer_balance',
            'argument': {
                'type': 'object',
                'properties': {
                    'account_number': {
                        'type': 'string',
                        'description': 'the callers account number'
                    }
                }
            }
        }

    def generate_swml(self):
        swml = {
            'version': '1.0.0',
            'sections': {
                'main': [
                    {
                        'ai': {
                            'params': self.get_base_params(),
                            'voice': 'en-US-Standard-A',
                            'prompt': {
                                'text': self.prompt_text
                            },
                            'post_prompt': {
                                'text': 'Please summarize the conversation'
                            },
                            'SWAIG': {
                                'functions': self.get_functions()
                            }
                        }
                    }
                ]
            }
        }
        return json.dumps(swml)

    def gather_credit_card_number(self):
        # This SWML will transfer the caller outside of the LLM to gather the credit card number
        swml = {
            'action': [
                {
                    "say": "You are now able to securely enter your Credit Card Number",
                },
                {
                    "SWML": {
                        "sections": {
                            "main": [
                                {
                                    "prompt": {
                                        "play": "silence: 1",
                                        "speech_language": "en-US",
                                        "max_digits": 16,
                                        "initial_timeout": 10,
                                        "speech_hints": [
                                            "one",
                                            "two",
                                            "three",
                                            "four",
                                            "five",
                                            "six",
                                            "seven",
                                            "eight",
                                            "nine",
                                            "zero"
                                        ]
                                    }
                                },
                                {"transfer": f"{self.ngrok_url}/cc_digits"}
                            ]
                        }
                    },
                    "version": "1.0.0"
                }
            ],
            'response': "Success. The user has entered their credit card."
        }
        print (f"\n{swml}\n")
        return json.dumps(swml)


cc = Flask(__name__)

@cc.route('/ai', methods=['POST'])
def swml_main():
    assistant = AIPaymentSWML(ngrok_url)
    return assistant.generate_swml()

# SWAIG FUNCTIONS
@cc.route('/get_credit_card_number', methods=['POST'])
def generate_swml_cc_json():
    assistant = AIPaymentSWML(ngrok_url)
    return assistant.gather_credit_card_number()

@cc.route('/submit_payment', methods=['POST'])
def submit_payment():
    swml = {}
    if not cc:
        swml['response'] = "error: credit card number not found or not valid"

    else:
        parsed_data = request.json.get('argument', {}).get('parsed', [{}])[0]

        first_name = parsed_data.get('first_name', '')
        last_name = parsed_data.get('last_name', '')
        account_number = parsed_data.get('account_number', '')
        cvv = parsed_data.get('card_verification_value', '')
        exp = parsed_data.get('expiration_date', '')

        print ( f"Processing payment for {first_name} {last_name}:\nAcct No. {account_number}\n Credit Card: {cc}\n CVV: {cvv}\n EXP: {exp}\n"  )

        swml['response'] = "success"

    return json.dumps(swml)

@cc.route('/cc_digits', methods=['POST'])
def save_cc_digits_in_var():
  # Store CC number as var in code.  The Language Model will never see this data.
  global cc
  print ("\nStoring Credit card in a Variable inside the code and sending back to the AI Agent\n")
  vars_dict = request.json.get('vars', {})

  prompt_value = vars_dict.get('prompt_value')
  if not prompt_value:
      return ("error: a credit card number was not provided"), 400

  # Save the credit card number to the global variable.  Return OK to the AI
  cc = prompt_value
  return ("ok"), 200

@cc.route('/get_customer_balance', methods=['POST'])
def get_customer_balance():
    swml = {}

    db = sqlite3.connect("customer.db")
    db.row_factory = sqlite3.Row
    cursor = db.cursor()

    parsed_data = request.json.get('argument', {}).get('parsed', [{}])[0]
    account_number = parsed_data.get('account_number', '')

    rows = cursor.execute(
        "SELECT balance from customer where account_number = ?",
        (account_number,)
    ).fetchall()

    if not rows:
        swml['response'] = "error: account number not found"
    else:
        for row in rows:
            balance = row['balance']
            swml['response'] = f"Your current balance is ${balance}."

    return json.dumps(swml)


if __name__ == '__main__':
    cc.run(port='5000', host='0.0.0.0', debug=True)