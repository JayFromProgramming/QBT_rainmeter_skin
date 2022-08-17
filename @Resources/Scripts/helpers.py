import json
import typing


class APIMessageTX:

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __str__(self):
        """Dump the api content to json"""
        return json.dumps(self.kwargs)

    def encode(self, encoding):
        """Encode the api content to bytes"""
        return self.__str__().encode(encoding) + b"\n\r"


class APIMessageRX:

    def __init__(self, json_raw: typing.Union[str, bytes]):
        """Load the api content from bytes"""
        if isinstance(json_raw, bytes):
            json_raw = json_raw.decode('utf-8')
        try:
            self.__dict__.update(json.loads(json_raw))  # Load the json into the locals()
        except json.decoder.JSONDecodeError:
            self.__dict__ = {"error": "Invalid JSON"}
            raise Exception("Invalid JSON")

    def __str__(self):
        """Dump the api content to json"""
        return json.dumps(self.__dict__)

    def encode(self, encoding):
        """Encode the api content to bytes"""
        return self.__str__().encode(encoding) + b"\n\r"
