import json
import requests
import sys
import os
import re
from urllib.parse import urlencode

# Disable SSL warnings if needed
requests.packages.urllib3.disable_warnings()

COLLECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ZeepLive_Complete_API_Collection_FIXED (2).json")

class ZeepLiveAPI:
    def __init__(self):
        self.session = requests.Session()
        self.variables = {}
        self.folders = []
        self.all_endpoints = []
        self.load_collection()

    def load_collection(self):
        with open(COLLECTION_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Load variables
        for v in data.get('variable', []):
            self.variables[v['key']] = v.get('value', '')

        # Override with correct base URL and credentials
        self.variables['base_url'] = 'https://testingphp.zeep.live/api'
        self.variables['username'] = 'fvista002@gmail.com'
        self.variables['password'] = '245645'
        self.variables['mobile'] = 'fvista002@gmail.com'

        # Load folders and endpoints
        self._parse_items(data.get('item', []), self.folders, self.all_endpoints)
        print(f"Loaded {len(self.all_endpoints)} endpoints from {len(self.folders)} folders")

    def _parse_items(self, items, folders_list, endpoints_list, parent_name=""):
        for item in items:
            if 'item' in item:
                folder = {
                    'name': item['name'],
                    'endpoints': []
                }
                self._parse_items(item['item'], folders_list, endpoints_list, item['name'])
                folder['endpoints'] = [e for e in endpoints_list if e.get('folder') == item['name']]
                folders_list.append(folder)
            elif 'request' in item:
                req = item['request']
                url = req.get('url', {})
                raw_url = url.get('raw', '') if isinstance(url, dict) else url

                endpoint = {
                    'name': item['name'],
                    'folder': parent_name,
                    'method': req.get('method', 'GET'),
                    'url': raw_url,
                    'headers': req.get('header', []),
                    'body': req.get('body', {}),
                    'auth': req.get('auth', {}),
                    'event': item.get('event', [])
                }
                endpoints_list.append(endpoint)

    def resolve_variable(self, text):
        if not isinstance(text, str):
            return text
        def replacer(match):
            key = match.group(1)
            return self.variables.get(key, match.group(0))
        return re.sub(r'\{\{(\w+)\}\}', replacer, text)

    def build_headers(self, endpoint):
        headers = {}
        for h in endpoint.get('headers', []):
            if h.get('disabled'):
                continue
            key = h.get('key', '')
            value = self.resolve_variable(h.get('value', ''))
            headers[key] = value
        return headers

    def build_body(self, endpoint):
        body_config = endpoint.get('body', {})
        if not body_config:
            return None, None

        mode = body_config.get('mode', '')

        if mode == 'formdata':
            data = {}
            for field in body_config.get('formdata', []):
                if field.get('disabled'):
                    continue
                key = field.get('key', '')
                value = self.resolve_variable(field.get('value', ''))
                data[key] = value
            return data, 'form'

        elif mode == 'urlencoded':
            data = {}
            for field in body_config.get('urlencoded', []):
                if field.get('disabled'):
                    continue
                key = field.get('key', '')
                value = self.resolve_variable(field.get('value', ''))
                data[key] = value
            return data, 'urlencoded'

        elif mode == 'raw':
            raw = self.resolve_variable(body_config.get('raw', ''))
            try:
                return json.loads(raw), 'json'
            except:
                return raw, 'raw'

        return None, None

    def execute_endpoint(self, endpoint):
        method = endpoint['method'].upper()
        url = self.resolve_variable(endpoint['url'])
        headers = self.build_headers(endpoint)
        body_data, body_type = self.build_body(endpoint)

        print(f"\n{'='*60}")
        print(f"  {method} {url}")
        print(f"{'='*60}")

        if headers:
            print(f"\n  Headers:")
            for k, v in headers.items():
                display_v = v[:80] + '...' if len(v) > 80 else v
                print(f"    {k}: {display_v}")

        if body_data:
            print(f"\n  Body ({body_type}):")
            if isinstance(body_data, dict):
                for k, v in body_data.items():
                    display_v = str(v)[:80] + '...' if len(str(v)) > 80 else str(v)
                    print(f"    {k}: {display_v}")
            else:
                print(f"    {str(body_data)[:200]}")

        print(f"\n  Sending request...")

        try:
            if method == 'GET':
                resp = self.session.get(url, headers=headers, verify=False, timeout=30)
            elif method == 'POST':
                if body_type == 'json':
                    resp = self.session.post(url, headers=headers, json=body_data, verify=False, timeout=30)
                elif body_type == 'urlencoded':
                    resp = self.session.post(url, headers=headers, data=body_data, verify=False, timeout=30)
                elif body_type == 'form':
                    resp = self.session.post(url, headers=headers, data=body_data, verify=False, timeout=30)
                elif body_type == 'raw':
                    resp = self.session.post(url, headers=headers, data=body_data, verify=False, timeout=30)
                else:
                    resp = self.session.post(url, headers=headers, verify=False, timeout=30)
            elif method == 'PUT':
                resp = self.session.put(url, headers=headers, json=body_data, verify=False, timeout=30)
            elif method == 'DELETE':
                resp = self.session.delete(url, headers=headers, verify=False, timeout=30)
            else:
                resp = self.session.request(method, url, headers=headers, verify=False, timeout=30)

            print(f"\n  Status: {resp.status_code}")
            print(f"  Response:")

            try:
                resp_json = resp.json()
                print(json.dumps(resp_json, indent=2, ensure_ascii=False))

                # Process post-request scripts (extract token, profile_id etc.)
                self._process_test_scripts(endpoint, resp_json)

                return resp_json
            except:
                text = resp.text[:2000]
                print(f"  {text}")
                return resp.text

        except requests.exceptions.ConnectionError as e:
            print(f"\n  CONNECTION ERROR: {e}")
            return None
        except requests.exceptions.Timeout:
            print(f"\n  TIMEOUT: Request took more than 30 seconds")
            return None
        except Exception as e:
            print(f"\n  ERROR: {type(e).__name__}: {e}")
            return None

    def _process_test_scripts(self, endpoint, resp_json):
        """Process Postman test scripts to extract variables like token, profile_id"""
        for event in endpoint.get('event', []):
            if event.get('listen') == 'test':
                script_lines = event.get('script', {}).get('exec', [])
                script = '\n'.join(script_lines)

                # Extract variable assignments from Postman scripts
                # Pattern: pm.collectionVariables.set("key", value)
                set_patterns = re.findall(r'pm\.collectionVariables\.set\(["\'](\w+)["\'],\s*(.+?)\)', script)
                for key, value_expr in set_patterns:
                    # Try to resolve from response
                    try:
                        if 'res.result.token' in value_expr or 'token' in value_expr:
                            if isinstance(resp_json, dict):
                                result = resp_json.get('result', {})
                                if isinstance(result, dict) and 'token' in result:
                                    self.variables['auth_token'] = result['token']
                                    print(f"\n  >> Saved auth_token: {result['token'][:50]}...")

                        if 'res.result.profile_id' in value_expr or 'profile_id' == key:
                            if isinstance(resp_json, dict):
                                result = resp_json.get('result', {})
                                if isinstance(result, dict) and 'profile_id' in result:
                                    self.variables['profile_id'] = str(result['profile_id'])
                                    print(f"  >> Saved profile_id: {result['profile_id']}")

                        if key == 'name' and isinstance(resp_json, dict):
                            result = resp_json.get('result', {})
                            if isinstance(result, dict) and 'name' in result:
                                self.variables['name'] = result.get('name', '')

                        if key == 'gender' and isinstance(resp_json, dict):
                            result = resp_json.get('result', {})
                            if isinstance(result, dict) and 'gender' in result:
                                self.variables['gender'] = result.get('gender', '')

                        if key == 'mobile' and isinstance(resp_json, dict):
                            result = resp_json.get('result', {})
                            if isinstance(result, dict) and 'mobile' in result:
                                self.variables['mobile'] = str(result.get('mobile', ''))
                    except Exception:
                        pass

    def show_folders(self):
        print(f"\n{'='*60}")
        print(f"  ZEEPLIVE API - FOLDER LIST")
        print(f"{'='*60}")
        for i, folder in enumerate(self.folders):
            print(f"  [{i+1:2d}] {folder['name']} ({len(folder['endpoints'])} endpoints)")
        print(f"\n  [0] Run Login First (Recommended)")
        print(f"  [v] View/Edit Variables")
        print(f"  [q] Quit")

    def show_endpoints(self, folder_idx):
        folder = self.folders[folder_idx]
        print(f"\n{'='*60}")
        print(f"  {folder['name']}")
        print(f"{'='*60}")
        for i, ep in enumerate(folder['endpoints']):
            print(f"  [{i+1:2d}] {ep['method']:6s} {ep['name']}")
        print(f"\n  [a] Run ALL endpoints in this folder")
        print(f"  [b] Back to folders")

    def show_variables(self):
        print(f"\n{'='*60}")
        print(f"  CURRENT VARIABLES")
        print(f"{'='*60}")
        for k, v in self.variables.items():
            display_v = v[:60] + '...' if len(str(v)) > 60 else v
            print(f"  {k}: {display_v}")
        print(f"\n  Enter 'key=value' to update a variable, or 'b' to go back")

    def login(self):
        """Run the login endpoint"""
        login_ep = None
        for ep in self.all_endpoints:
            if 'Login User' in ep['name'] or 'device-manual-login' in ep['url']:
                login_ep = ep
                break

        if not login_ep:
            print("  Login endpoint not found!")
            return

        print("\n  Logging in with current credentials...")
        print(f"  Username: {self.variables.get('username', 'N/A')}")
        print(f"  Password: {self.variables.get('password', 'N/A')}")

        result = self.execute_endpoint(login_ep)

        if isinstance(result, dict) and result.get('success'):
            print(f"\n  LOGIN SUCCESSFUL!")
            print(f"  Token: {self.variables.get('auth_token', 'N/A')[:50]}...")
            print(f"  Profile ID: {self.variables.get('profile_id', 'N/A')}")
        else:
            print(f"\n  LOGIN FAILED!")
            if isinstance(result, dict):
                print(f"  Message: {result.get('message', 'Unknown error')}")

    def run(self):
        print(f"\n{'='*60}")
        print(f"  ZEEPLIVE API RUNNER")
        print(f"  Loaded from Postman Collection")
        print(f"{'='*60}")

        while True:
            self.show_folders()
            choice = input("\n  Select folder number: ").strip().lower()

            if choice == 'q':
                print("  Bye!")
                break
            elif choice == '0':
                self.login()
                input("\n  Press Enter to continue...")
            elif choice == 'v':
                while True:
                    self.show_variables()
                    var_input = input("\n  > ").strip()
                    if var_input.lower() == 'b':
                        break
                    if '=' in var_input:
                        key, value = var_input.split('=', 1)
                        self.variables[key.strip()] = value.strip()
                        print(f"  Updated {key.strip()} = {value.strip()}")
            elif choice.isdigit():
                folder_idx = int(choice) - 1
                if 0 <= folder_idx < len(self.folders):
                    while True:
                        self.show_endpoints(folder_idx)
                        ep_choice = input("\n  Select endpoint number: ").strip().lower()

                        if ep_choice == 'b':
                            break
                        elif ep_choice == 'a':
                            folder = self.folders[folder_idx]
                            for ep in folder['endpoints']:
                                self.execute_endpoint(ep)
                                print()
                            input("\n  Press Enter to continue...")
                        elif ep_choice.isdigit():
                            ep_idx = int(ep_choice) - 1
                            folder = self.folders[folder_idx]
                            if 0 <= ep_idx < len(folder['endpoints']):
                                self.execute_endpoint(folder['endpoints'][ep_idx])
                                input("\n  Press Enter to continue...")
                            else:
                                print("  Invalid endpoint number!")
                        else:
                            print("  Invalid choice!")
                else:
                    print("  Invalid folder number!")
            else:
                print("  Invalid choice!")


if __name__ == '__main__':
    api = ZeepLiveAPI()
    api.run()
