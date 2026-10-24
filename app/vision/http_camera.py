"""Pull fresh JPEGs from an explicitly selected local camera's /capture endpoint.
No video backlog; remote capture-clock alignment is not claimed by this adapter.
"""
import ipaddress
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

import numpy as np
from .model import read_jpeg


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class HttpCamera:
    def __init__(self, url, opener=None):
        parsed = urlsplit(url)
        if parsed.scheme!='http' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('Use http://LOCAL_CAMERA_IP/capture without credentials or fragment')
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            raise ValueError('Use the camera numeric LAN IP printed on serial') from None
        if not (address.is_private or address.is_loopback) or address.is_unspecified or address.is_multicast:
            raise ValueError('HTTP camera URL must be an explicit private/loopback address')
        self.url, self.opener, self.closed = url, opener or build_opener(NoRedirect()), False
        self.captured_at = None

    def set(self, *args): return False
    def isOpened(self): return not self.closed
    def release(self): self.closed = True

    def read(self):
        if self.closed: return False, None
        self.captured_at = None
        began = time.monotonic()
        try:
            request = Request(self.url,headers={'Cache-Control':'no-cache','Accept':'image/jpeg'})
            with self.opener.open(request,timeout=.7) as response:
                if response.headers.get_content_type()!='image/jpeg': return False, None
                data = response.read(1_000_001)
                age = response.headers.get('X-Stride-Frame-Age-Us')
            # Validate format/dimensions before expanding the image to an array.
            image = read_jpeg(data)
            if age is not None:
                age_us = int(age)
                if age_us < 0 or age_us >= 1_000_000: return False, None
                # Subtract reported camera age from request START, making transit
                # conservative without comparing the two devices' epoch clocks.
                self.captured_at = began - age_us/1_000_000
                if time.monotonic()-self.captured_at >= 1: return False, None
            return True, np.ascontiguousarray(np.asarray(image)[:,:,::-1])
        except (OSError, ValueError):
            return False, None
