import http.client
import json
import socket
import threading
import unittest
from urllib.parse import quote

from backend.server import Handler
from backend.services import ScutService


class ServerTests(unittest.TestCase):
    def setUp(self):
        from http.server import ThreadingHTTPServer
        Handler.service = ScutService(0); self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self): self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,body=None,headers=None):
        request_headers = {"Content-Type":"application/json"} if body is not None else {}
        request_headers.update(headers or {})
        c=http.client.HTTPConnection("127.0.0.1",self.port);c.request("POST" if body is not None else "GET",path,body=json.dumps(body) if body is not None else None,headers=request_headers);r=c.getresponse();data=json.loads(r.read());c.close();return r.status,data
    def test_status_contract(self):
        code,data=self.request("/api/status");self.assertEqual(200,code);self.assertIn("mode",data);self.assertNotIn("apiKey",json.dumps(data))
    def test_invalid_mode_uses_consistent_error(self):
        code,data=self.request("/api/mode",{"mode":"DANGER"});self.assertEqual(422,code);self.assertEqual("VALIDATION_ERROR",data["error"]["code"])
    def test_test_alert_does_not_need_anymodel(self):
        code,data=self.request("/api/alerts/test",{});self.assertEqual(200,code);self.assertTrue(data["ok"])

    def test_rejects_non_json_state_changing_requests(self):
        code,data=self.request("/api/mode",{"mode":"OFF"},{"Content-Type":"text/plain"})
        self.assertEqual(415,code)
        self.assertEqual("JSON_REQUIRED",data["error"]["code"])

    def test_rejects_cross_origin_state_changing_requests(self):
        code,data=self.request("/api/mode",{"mode":"OFF"},{"Origin":"https://attacker.example"})
        self.assertEqual(403,code)
        self.assertEqual("ORIGIN_DENIED",data["error"]["code"])

    def test_allows_same_origin_browser_request(self):
        origin=f"http://127.0.0.1:{self.port}"
        code,data=self.request("/api/mode",{"mode":"OFF"},{"Origin":origin})
        self.assertEqual(200,code)
        self.assertEqual("OFF",data["mode"])

    def test_rejects_non_local_host_header(self):
        code,data=self.request("/health",headers={"Host":"attacker.example"})
        self.assertEqual(400,code)
        self.assertEqual("HOST_DENIED",data["error"]["code"])

    def test_private_rest_boundary_accepts_only_loopback_clients(self):
        self.assertTrue(Handler.is_loopback_address("127.0.0.1"))
        self.assertTrue(Handler.is_loopback_address("::1"))
        self.assertFalse(Handler.is_loopback_address("192.168.1.22"))
        self.assertFalse(Handler.is_loopback_address("203.0.113.18"))

    def test_packaged_renderer_websocket_origin_requires_loopback(self):
        packaged = object.__new__(Handler)
        packaged.headers = {"Host": f"127.0.0.1:{self.port}", "Origin": "file://"}
        packaged.client_address = ("127.0.0.1", 0)
        self.assertTrue(packaged.same_origin_websocket_request())

        remote = object.__new__(Handler)
        remote.headers = {"Host": f"127.0.0.1:{self.port}", "Origin": "file://"}
        remote.client_address = ("192.168.1.22", 0)
        self.assertFalse(remote.same_origin_websocket_request())

    def test_history_and_alerts_proxy_only_real_control_plane_results(self):
        class Plane:
            def list_history(self, cursor=None, limit=25): return {"conversations": [{"id": "conversation-1"}], "nextCursor": cursor, "limit": limit}
            def list_alerts(self, cursor=None, limit=25): return {"alerts": [{"id": "alert-1"}], "nextCursor": cursor, "limit": limit}
        Handler.service.control_plane = Plane()

        code, history = self.request(f"/api/history?limit=12&cursor={quote('2026-09-09T10:00:00Z')}")
        self.assertEqual(200, code)
        self.assertEqual("conversation-1", history["conversations"][0]["id"])
        self.assertEqual(12, history["limit"])
        code, alerts = self.request("/api/alerts?limit=7")
        self.assertEqual(200, code)
        self.assertEqual("alert-1", alerts["alerts"][0]["id"])

    def test_conversation_detail_and_delete_validate_uuid(self):
        conversation_id = "00000000-0000-4000-8000-000000000001"
        class Plane:
            def conversation_detail(self, value): return {"conversation": {"id": value, "segments": []}}
            def delete_conversation(self, value): return value == conversation_id
        Handler.service.control_plane = Plane()

        code, detail = self.request(f"/api/history/{conversation_id}")
        self.assertEqual(200, code)
        self.assertEqual(conversation_id, detail["conversation"]["id"])
        code, deleted = self.request("/api/history/delete", {"conversationId": conversation_id})
        self.assertEqual(200, code)
        self.assertTrue(deleted["deleted"])
        code, error = self.request("/api/history/not-an-id")
        self.assertEqual(422, code)
        self.assertEqual("VALIDATION_ERROR", error["error"]["code"])
