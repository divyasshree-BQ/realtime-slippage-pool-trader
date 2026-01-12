import uuid
from typing import Dict, Callable, Optional
from confluent_kafka import Consumer, KafkaError, KafkaException
from google.protobuf.message import DecodeError
import config

from evm import dex_pool_block_message_pb2
from utils.protobuf_utils import protobuf_to_dict, convert_hex_to_int


class BitqueryStream:
    """Bitquery Kafka stream consumer for DEX pool events."""
    
    def __init__(self, topic: str = 'eth.dexpools.proto', group_id_suffix: Optional[str] = None):
        """
        Initialize Bitquery stream consumer.
        
        Args:
            topic: Kafka topic to subscribe to
            group_id_suffix: Optional suffix for consumer group ID
        """
        self.topic = topic
        group_id_suffix = group_id_suffix or uuid.uuid4().hex
        
        conf = {
            'bootstrap.servers': 'rpk0.bitquery.io:9092,rpk1.bitquery.io:9092,rpk2.bitquery.io:9092',
            'group.id': f'{config.eth_username}-group-{group_id_suffix}',
            'session.timeout.ms': 30000,
            'security.protocol': 'SASL_PLAINTEXT',
            'ssl.endpoint.identification.algorithm': 'none',
            'sasl.mechanisms': 'SCRAM-SHA-512',
            'sasl.username': config.eth_username,
            'sasl.password': config.eth_password,
            'auto.offset.reset': 'latest',
        }
        
        self.consumer = Consumer(conf)
        self.consumer.subscribe([topic])
    
    def parse_message(self, buffer: bytes) -> Optional[Dict]:
        """
        Parse a Kafka message buffer into a dictionary.
        
        Args:
            buffer: Raw message bytes from Kafka
            
        Returns:
            Parsed dictionary or None if parsing fails
        """
        try:
            if not buffer:
                return None
            
            price_feed = dex_pool_block_message_pb2.DexPoolBlockMessage()
            price_feed.ParseFromString(buffer)
            
            data_dict = protobuf_to_dict(price_feed, encoding='hex')
            data_dict = convert_hex_to_int(data_dict)
            
            return data_dict
        except (DecodeError, Exception):
            return None
    
    def poll(self, timeout: float = 1.0) -> Optional[Dict]:
        """
        Poll for a new message from Kafka.
        
        Args:
            timeout: Poll timeout in seconds
            
        Returns:
            Parsed message dictionary or None if no message
        """
        msg = self.consumer.poll(timeout=timeout)
        
        if msg is None:
            return None
        
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                return None
            else:
                raise KafkaException(msg.error())
        
        buffer = msg.value()
        return self.parse_message(buffer)
    
    def stream(self, callback: Callable[[Dict], None]):
        """
        Stream messages and call callback for each message.
        
        Args:
            callback: Function to call with each parsed message
        """
        try:
            while True:
                data_dict = self.poll()
                if data_dict is not None:
                    callback(data_dict)
        except KeyboardInterrupt:
            print("Stopping stream...")
        finally:
            self.close()
    
    def close(self):
        """Close the Kafka consumer."""
        self.consumer.close()

