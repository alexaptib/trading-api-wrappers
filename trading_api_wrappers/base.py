import json
import time
from enum import Enum
from urllib.parse import urlparse

# pip
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# local
from . import errors
from .common import clean_parameters

TIMEOUT = 30
RETRY = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=(400, 401, 403, 404, 408, 429, 500, 502, 503, 504),
)


class Server(object):

    def __init__(self, protocol, host, version=None):
        url = f'{protocol}://{host}'
        if version:
            url = f'{url}/{version}'
        self.PROTOCOL = protocol
        self.HOST = host
        self.VERSION = version
        self.URL = url


class Client(object):
    error_key = ''
    enable_rate_limit = True
    rate_limit = 1000  # in milliseconds (seconds * 1E3)

    def __init__(self, server: Server, timeout: int=TIMEOUT,
                 retry: (bool, int, Retry)=None):
        self.SERVER = server
        self.TIMEOUT = timeout
        # Set session
        session = requests.Session()
        if retry is True:
            retry = RETRY
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        self.session = session
        self.last_request_timestamp = 0

    def get(self, endpoint, params=None):
        return self._request('get', endpoint, params=params)

    def post(self, endpoint, data=None):
        return self._request('post', endpoint, data=data)

    def put(self, endpoint, data=None):
        return self._request('put', endpoint, data=data)

    def patch(self, endpoint, data=None):
        return self._request('patch', endpoint, data=data)

    def delete(self, endpoint, data=None):
        return self._request('delete', endpoint, data=data)

    def _request(self, method, endpoint, params=None, data=None):
        # Rate limit requests
        if self.enable_rate_limit:
            self.throttle()
        self.last_request_timestamp = self.milliseconds()
        # Prepare the request
        url, path = self.url_path_for(endpoint)
        data = self._encode_data(data)
        request = self.sign(method, path, params, data)
        # Send the request
        response = self.session.request(
            method,
            url=url,
            headers=request.get('headers'),
            params=request.get('params', params),
            data=request.get('data', data),
            verify=True,
            timeout=self.TIMEOUT)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise errors.InvalidResponse(response) from e
        # Decode response
        return self._decode_data(response)

    def sign(self, method, path, params=None, data=None):
        return {}

    def _encode_data(self, data):
        data = clean_parameters(data or {})
        return json.dumps(data) if data else data

    def _decode_data(self, response):
        try:
            json_resp = response.json()
        except json.decoder.JSONDecodeError as e:
            raise errors.DecodeError() from e
        if isinstance(json_resp, dict):
            if bool(json_resp.get(self.error_key, False)):
                raise errors.InvalidResponse(response)
        return json_resp

    def url_for(self, endpoint):
        return f'{self.SERVER.URL}/{endpoint}'

    def url_path_for(self, endpoint):
        url = self.url_for(endpoint)
        path = urlparse(url).path
        return url, path

    def throttle(self):
        now = float(self.milliseconds())
        elapsed = now - self.last_request_timestamp
        if elapsed < self.rate_limit:
            delay = self.rate_limit - elapsed
            time.sleep(delay / 1E3)

    def nonce(self):
        return str(self.microseconds())

    @staticmethod
    def seconds():
        return int(time.time())

    @staticmethod
    def milliseconds():
        return int(time.time() * 1E3)

    @staticmethod
    def microseconds():
        return int(time.time() * 1E6)

    def __del__(self):
        if self.session:
            self.session.close()


class _Enum(Enum):
    @staticmethod
    def _format_value(value):
        return str(value).upper()

    @classmethod
    def check(cls, value):
        if value is None:
            return value
        if type(value) is cls:
            return value
        try:
            return cls[cls._format_value(value)]
        except KeyError:
            return cls._missing_(value)

    def __str__(self):
        return self.value


class _Currency(_Enum):
    @property
    def value(self):
        return super(_Currency, self).value['value']

    @property
    def decimals(self):
        return super(_Currency, self).value.get('decimals', 2)


class _Market(_Enum):
    @staticmethod
    def _format_value(value):
        value = str(value).replace('-', '')
        value = f'{value[:3]}_{value[3:]}'
        return value.upper()

    @property
    def value(self):
        return super(_Market, self).value['value']

    @property
    def base(self):
        return super(_Market, self).value['base']

    @property
    def quote(self):
        return super(_Market, self).value['quote']
