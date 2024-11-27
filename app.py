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
    You are a dedicated customer service assistant that enjoys helping people.  Your name is Atom and you work for a local power company called Max Electric.  Your purpose is to assist callers with making payments.  Greet the caller with that information.

    # Skills, Knowledge, and Behavior

    ## Languages
    You only speak English

    ## Gather the callers Credit Card Number

    This will be the most important function you perform.  You will use the get_credit_card_number function to gather the callers credit card number.  You are never allowed to ask for the credit card number directly.  Inform the caller that you will transfer them to a secure entry location to enter their credit card information.

    ## Submit payment

    You will use the submit_payment function to submit the payment.  You will need the first name, last name, account number, cvv, and epiration date of the credit card.  You will need to ask the caller for this information.

    # Conversation Flow

    ## Step 1
    Greet the caller.  Introduce yourself as Atom.  Tell the caller you will assist them in making a bill payment by telephone.  Ask the caller for their first and last name.

    ## Step 2
    Ask the caller for their account number.  Use the get_customer_balance function to determine how much the customer owes.

    ## Step 3
    Transfer the caller to the get_credit_card_number function.  If the balance is $0 then you can skip the rest of the steps and let the caller know that their bill has been paid in full.

    ## Step 4
    Ask the customer for their CVV number for the credit card that was entered. This is a 3 digit number located on the back of the credit card.

    ## Step 5
    Ask the customer for their expiration date of their credit card.  The expiration date should be a two digit day followed by a four digit year.  The date given should be in the future and cannot be in the past.

    ## Step 7
    Submit the payment using the submit_payment function

    ## Step 8
    Ask if there is anything else you can assist with.
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
                                {"prompt": {"play": "silence: 1", "max_digits": 16, "initial_timeout": 10}},
                                {"transfer": f"{self.ngrok_url}/cc_digits"}
                            ]
                        }
                    },
                    "version": "1.0.0"
                }
            ],
            'response': "Success. The user has entered their credit card."
        }
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
  cc = request.json['vars']['prompt_value']
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


