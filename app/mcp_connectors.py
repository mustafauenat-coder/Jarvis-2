"""MCP Streamable HTTP connector access; credentials stay in Jarvis' private store."""
import ipaddress
import json
import socket
from urllib.parse import urlsplit

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class ConnectorError(Exception):
    pass


def validate_endpoint(url):
    try:
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.hostname and not parts.username and not parts.password:
            host = parts.hostname
            try:
                ip = ipaddress.ip_address(host)
                if not ip.is_global:
                    raise ConnectorError("Remote MCP-Endpunkte müssen öffentlich erreichbar sein.")
            except ValueError:
                addresses = {item[4][0] for item in socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)}
                if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                    raise ConnectorError("Der MCP-Server verweist auf eine private Netzwerkadresse.")
            if parts.query or parts.fragment:
                raise ConnectorError("Bitte Zugangsdaten nicht in URL-Parametern hinterlegen.")
            return
        if parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"} and not parts.username and not parts.password:
            if parts.query or parts.fragment:
                raise ConnectorError("Bitte Zugangsdaten nicht in URL-Parametern hinterlegen.")
            return
    except (OSError, ValueError):
        pass
    raise ConnectorError("Erlaubt sind HTTPS-MCP-Adressen oder HTTP auf localhost.")


def public_connector(item):
    return {"id": item["id"], "name": item["name"], "url": item["url"],
            "has_token": bool(item.get("token")), "enabled": item.get("enabled", True)}


def _session(item):
    headers = {"Authorization": "Bearer " + item["token"]} if item.get("token") else None
    return streamablehttp_client(item["url"], headers=headers)


async def list_tools(item):
    validate_endpoint(item["url"])
    async with _session(item) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()
            return [{"name": tool.name, "description": tool.description or "",
                     "input_schema": tool.inputSchema,
                     "annotations": tool.annotations.model_dump(exclude_none=True) if tool.annotations else {}}
                    for tool in response.tools]


async def call_tool(item, name, arguments):
    validate_endpoint(item["url"])
    async with _session(item) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.call_tool(name, arguments)
            content = []
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    content.append(block.text)
                else:
                    content.append("[" + str(getattr(block, "type", "MCP-Inhalt")) + "]")
            result = response.structuredContent if response.structuredContent is not None else "\n".join(content)
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, default=str)
            return {"is_error": response.isError, "result": result[:20000]}

