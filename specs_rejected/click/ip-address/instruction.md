# Feature Request: IP Address Parameter Type

## Description
The `IPAddress` parameter type is required to convert a string into an `ipaddress.IPv4Address` or `ipaddress.IPv6Address` object. It should validate IPv4 and IPv6 addresses and networks using the `ipaddress` module. The type should accept strings and output the corresponding `ipaddress.IPv4Address` or `ipaddress.IPv6Address` objects. If the input is invalid, it should raise a `BadParameter` with an appropriate error message.

## Signature
```python
class IPAddress(ParamType):
    def __init__(self, network: bool = False) -> None:
        self.network = network

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> ip_address:
        # Conversion logic here
```

## Behavior
### Normal Input
- **IPv4 Address**: Input like `'192.168.1.1'` should be converted to an `ipaddress.IPv4Address` object.
- **IPv6 Address**: Input like `'2001:0db8:85a3:0000:0000:8a2e:0370:7334'` should be converted to an `ipaddress.IPv6Address` object.
- **IPv4 Network**: Input like `'192.168.1.0/24'` should be converted to an `ipaddress.IPv4Network` object if `network=True`.
- **IPv6 Network**: Input like `'2001:0db8:85a3:0000:0000:8a2e:0370:7334/64'` should be converted to an `ipaddress.IPv6Network` object if `network=True`.

### Edge Cases
- **Empty String**: Input like `''` should raise a `BadParameter` with the message `"' is not a valid IP address."`.
- **Non-String Input**: Input like `12345` should raise a `BadParameter` with the message `"'12345' is not a valid IP address."`.
- **Invalid IPv4 Address**: Input like `'256.256.256.256'` should raise a `BadParameter` with the message `"'256.256.256.256' is not a valid IP address."`.
- **Invalid IPv6 Address**: Input like `'2001:0db8:85a3:0000:0000:8a2e:0370:7334:1'` should raise a `BadParameter` with the message `"'2001:0db8:85a3:0000:0000:8a2e:0370:7334:1' is not a valid IP address."`.
- **Invalid IPv4 Network**: Input like `'192.168.1.0/33'` should raise a `BadParameter` with the message `"'192.168.1.0/33' is not a valid IP network."`.
- **Invalid IPv6 Network**: Input like `'2001:0db8:85a3:0000:0000:8a2e:0370:7334/129'` should raise a `BadParameter` with the message `"'2001:0db8:85a3:0000:0000:8a2e:0370:7334/129' is not a valid IP network."`.
- **IPv4 with Leading Zero**: Input like `'192.168.01.1'` should raise a `BadParameter` with the message `"'192.168.01.1' is not a valid IP address."`.
- **IPv6 with Leading Zero**: Input like `'2001:0db8:85a3:0000:0000:8a2e:0370:0001'` should raise a `BadParameter` with the message `"'2001:0db8:85a3:0000:0000:8a2e:0370:0001' is not a valid IP address."`.
- **IPv4 with Trailing Zero**: Input like `'192.168.1.0'` should raise a `BadParameter` with the message `"'192.168.1.0' is not a valid IP address."`.

## Error Messages
- `"' is not a valid IP address."`
- `"'12345' is not a valid IP address."`
- `"'256.256.256.256' is not a valid IP address."`
- `"'2001:0db8:85a3:0000:0000:8a2e:0370:7334:1' is not a valid IP address."`
- `"'192.168.1.0/33' is not a valid IP network."`
- `"'2001:0db8:85a3:0000:0000:8a2e:0370:7334/129' is not a valid IP network."`
- `"'192.168.01.1' is not a valid IP address."`
- `"'2001:0db8:85a3:0000:0000:8a2e:0370:0001' is not a valid IP address."`
- `"'192.168.1.0' is not a valid IP address."`

## Notes
- The `network` parameter determines whether the input should be validated as an IP address or a network.
- The `convert` method should handle both IPv4 and IPv6 addresses and networks.
- The `BadParameter` exception should be raised with an appropriate error message for invalid inputs.
