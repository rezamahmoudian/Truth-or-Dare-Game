from dataclasses import dataclass


@dataclass
class DomainError(Exception):
    """A rejection the user should see, with a stable code for the client.

    Carried identically over HTTP and the WebSocket so the client has one way
    to read a refusal regardless of which transport produced it.
    """

    code: str
    message: str
    status: int = 400

    def __str__(self) -> str:
        return self.message
