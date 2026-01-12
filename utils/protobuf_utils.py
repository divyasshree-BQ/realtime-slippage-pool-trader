"""
Protobuf conversion utilities for Bitquery stream messages.
"""

import base58
from typing import Dict
from google.protobuf.descriptor import FieldDescriptor


def convert_bytes(value, encoding='base58'):
    """Convert bytes to string representation."""
    if encoding == 'base58':
        return base58.b58encode(value).decode()
    return '0x' + value.hex()


def protobuf_to_dict(msg, encoding='base58'):
    """Convert protobuf message to dictionary."""
    result = {}
    for field in msg.DESCRIPTOR.fields:
        value = getattr(msg, field.name)

        if field.label == FieldDescriptor.LABEL_REPEATED:
            if not value:
                continue
            result[field.name] = []
            for item in value:
                if field.type == FieldDescriptor.TYPE_MESSAGE:
                    result[field.name].append(protobuf_to_dict(item, encoding))
                elif field.type == FieldDescriptor.TYPE_BYTES:
                    result[field.name].append(convert_bytes(item, encoding))
                else:
                    result[field.name].append(item)

        elif field.containing_oneof:
            if msg.WhichOneof(field.containing_oneof.name) == field.name:
                if field.type == FieldDescriptor.TYPE_MESSAGE:
                    result[field.name] = protobuf_to_dict(value, encoding)
                elif field.type == FieldDescriptor.TYPE_BYTES:
                    result[field.name] = convert_bytes(value, encoding)
                else:
                    result[field.name] = value

        elif field.type == FieldDescriptor.TYPE_MESSAGE:
            if msg.HasField(field.name):
                result[field.name] = protobuf_to_dict(value, encoding)

        elif field.type == FieldDescriptor.TYPE_BYTES:
            result[field.name] = convert_bytes(value, encoding)

        else:
            result[field.name] = value

    return result


def convert_hex_to_int(data):
    """Recursively convert hex strings to integers/floats for known numeric fields."""
    numeric_hex_fields = {
        'Number', 'BaseFee', 'ParentNumber', 'PreBalance', 'PostBalance',
        'MaxAmountIn', 'MaxAmountOut', 'MinAmountOut', 'MinAmountIn',
        'AmountCurrencyA', 'AmountCurrencyB', 'GasPrice', 'GasFeeCap', 'GasTipCap'
    }
    
    # Fields that should be numeric but might come as strings (decimal or hex)
    numeric_fields = {
        'SlippageBasisPoints', 'Price', 'AtoBPrice', 'BtoAPrice'
    }
    
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key in numeric_hex_fields and isinstance(value, str) and value:
                # Try hex conversion first
                try:
                    result[key] = int(value, 16)
                except ValueError:
                    # Try decimal conversion
                    try:
                        if '.' in value:
                            result[key] = float(value)
                        else:
                            result[key] = int(value)
                    except ValueError:
                        result[key] = value
            elif key in numeric_fields and isinstance(value, str) and value:
                # For numeric fields, try decimal first, then hex
                try:
                    if '.' in value:
                        result[key] = float(value)
                    else:
                        result[key] = int(value)
                except ValueError:
                    # Try hex as fallback
                    try:
                        result[key] = int(value, 16)
                    except ValueError:
                        result[key] = value
            elif isinstance(value, (dict, list)):
                result[key] = convert_hex_to_int(value)
            else:
                result[key] = value
        return result
    elif isinstance(data, list):
        return [convert_hex_to_int(item) for item in data]
    else:
        return data

