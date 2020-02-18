'''
DO NOT EDIT THIS FILE

This file is generated from the CDP specification. If you need to make changes,
edit the generator and regenerate all of the modules.

Domain: Security
Experimental: False
'''

from cdp.util import event_class, T_JSON_DICT
from dataclasses import dataclass
import enum
import typing


from deprecated.sphinx import deprecated


class CertificateId(int):
    '''
    An internal certificate ID value.
    '''
    def to_json(self) -> int:
        return self

    @classmethod
    def from_json(cls, json: int) -> 'CertificateId':
        return cls(json)

    def __repr__(self):
        return 'CertificateId({})'.format(super().__repr__())


class MixedContentType(enum.Enum):
    '''
    A description of mixed content (HTTP resources on HTTPS pages), as defined by
    https://www.w3.org/TR/mixed-content/#categories
    '''
    BLOCKABLE = "blockable"
    OPTIONALLY_BLOCKABLE = "optionally-blockable"
    NONE = "none"

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, json: str) -> 'MixedContentType':
        return cls(json)


class SecurityState(enum.Enum):
    '''
    The security level of a page or resource.
    '''
    UNKNOWN = "unknown"
    NEUTRAL = "neutral"
    INSECURE = "insecure"
    SECURE = "secure"
    INFO = "info"

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, json: str) -> 'SecurityState':
        return cls(json)


@dataclass
class SecurityStateExplanation:
    '''
    An explanation of an factor contributing to the security state.
    '''
    #: Security state representing the severity of the factor being explained.
    security_state: 'SecurityState'

    #: Title describing the type of factor.
    title: str

    #: Short phrase describing the type of factor.
    summary: str

    #: Full text explanation of the factor.
    description: str

    #: The type of mixed content described by the explanation.
    mixed_content_type: 'MixedContentType'

    #: Page certificate.
    certificate: typing.List[str]

    #: Recommendations to fix any issues.
    recommendations: typing.Optional[typing.List[str]] = None

    def to_json(self) -> T_JSON_DICT:
        json: T_JSON_DICT = dict()
        json['securityState'] = self.security_state.to_json()
        json['title'] = self.title
        json['summary'] = self.summary
        json['description'] = self.description
        json['mixedContentType'] = self.mixed_content_type.to_json()
        json['certificate'] = [i for i in self.certificate]
        if self.recommendations is not None:
            json['recommendations'] = [i for i in self.recommendations]
        return json

    @classmethod
    def from_json(cls, json: T_JSON_DICT) -> 'SecurityStateExplanation':
        return cls(
            security_state=SecurityState.from_json(json['securityState']),
            title=str(json['title']),
            summary=str(json['summary']),
            description=str(json['description']),
            mixed_content_type=MixedContentType.from_json(json['mixedContentType']),
            certificate=[str(i) for i in json['certificate']],
            recommendations=[str(i) for i in json['recommendations']] if 'recommendations' in json else None,
        )


@dataclass
class InsecureContentStatus:
    '''
    Information about insecure content on the page.
    '''
    #: Always false.
    ran_mixed_content: bool

    #: Always false.
    displayed_mixed_content: bool

    #: Always false.
    contained_mixed_form: bool

    #: Always false.
    ran_content_with_cert_errors: bool

    #: Always false.
    displayed_content_with_cert_errors: bool

    #: Always set to unknown.
    ran_insecure_content_style: 'SecurityState'

    #: Always set to unknown.
    displayed_insecure_content_style: 'SecurityState'

    def to_json(self) -> T_JSON_DICT:
        json: T_JSON_DICT = dict()
        json['ranMixedContent'] = self.ran_mixed_content
        json['displayedMixedContent'] = self.displayed_mixed_content
        json['containedMixedForm'] = self.contained_mixed_form
        json['ranContentWithCertErrors'] = self.ran_content_with_cert_errors
        json['displayedContentWithCertErrors'] = self.displayed_content_with_cert_errors
        json['ranInsecureContentStyle'] = self.ran_insecure_content_style.to_json()
        json['displayedInsecureContentStyle'] = self.displayed_insecure_content_style.to_json()
        return json

    @classmethod
    def from_json(cls, json: T_JSON_DICT) -> 'InsecureContentStatus':
        return cls(
            ran_mixed_content=bool(json['ranMixedContent']),
            displayed_mixed_content=bool(json['displayedMixedContent']),
            contained_mixed_form=bool(json['containedMixedForm']),
            ran_content_with_cert_errors=bool(json['ranContentWithCertErrors']),
            displayed_content_with_cert_errors=bool(json['displayedContentWithCertErrors']),
            ran_insecure_content_style=SecurityState.from_json(json['ranInsecureContentStyle']),
            displayed_insecure_content_style=SecurityState.from_json(json['displayedInsecureContentStyle']),
        )


class CertificateErrorAction(enum.Enum):
    '''
    The action to take when a certificate error occurs. continue will continue processing the
    request and cancel will cancel the request.
    '''
    CONTINUE = "continue"
    CANCEL = "cancel"

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, json: str) -> 'CertificateErrorAction':
        return cls(json)


def disable() -> typing.Generator[T_JSON_DICT,T_JSON_DICT,None]:
    '''
    Disables tracking security state changes.
    '''
    cmd_dict: T_JSON_DICT = {
        'method': 'Security.disable',
    }
    json = yield cmd_dict


def enable() -> typing.Generator[T_JSON_DICT,T_JSON_DICT,None]:
    '''
    Enables tracking security state changes.
    '''
    cmd_dict: T_JSON_DICT = {
        'method': 'Security.enable',
    }
    json = yield cmd_dict


def set_ignore_certificate_errors(
        ignore: bool
    ) -> typing.Generator[T_JSON_DICT,T_JSON_DICT,None]:
    '''
    Enable/disable whether all certificate errors should be ignored.

    :param ignore: If true, all certificate errors will be ignored.
    '''
    params: T_JSON_DICT = dict()
    params['ignore'] = ignore
    cmd_dict: T_JSON_DICT = {
        'method': 'Security.setIgnoreCertificateErrors',
        'params': params,
    }
    json = yield cmd_dict


@deprecated(version="1.3")
def handle_certificate_error(
        event_id: int,
        action: 'CertificateErrorAction'
    ) -> typing.Generator[T_JSON_DICT,T_JSON_DICT,None]:
    '''
    .. deprecated:: 1.3

    Handles a certificate error that fired a certificateError event.

    :param event_id: The ID of the event.
    :param action: The action to take on the certificate error.
    '''
    params: T_JSON_DICT = dict()
    params['eventId'] = event_id
    params['action'] = action.to_json()
    cmd_dict: T_JSON_DICT = {
        'method': 'Security.handleCertificateError',
        'params': params,
    }
    json = yield cmd_dict


@deprecated(version="1.3")
def set_override_certificate_errors(
        override: bool
    ) -> typing.Generator[T_JSON_DICT,T_JSON_DICT,None]:
    '''
    .. deprecated:: 1.3

    Enable/disable overriding certificate errors. If enabled, all certificate error events need to
    be handled by the DevTools client and should be answered with `handleCertificateError` commands.

    :param override: If true, certificate errors will be overridden.
    '''
    params: T_JSON_DICT = dict()
    params['override'] = override
    cmd_dict: T_JSON_DICT = {
        'method': 'Security.setOverrideCertificateErrors',
        'params': params,
    }
    json = yield cmd_dict


@deprecated(version="1.3")
@event_class('Security.certificateError')
@dataclass
class CertificateError:
    '''
    There is a certificate error. If overriding certificate errors is enabled, then it should be
    handled with the `handleCertificateError` command. Note: this event does not fire if the
    certificate error has been allowed internally. Only one client per target should override
    certificate errors at the same time.
    '''
    #: The ID of the event.
    event_id: int
    #: The type of the error.
    error_type: str
    #: The url that was requested.
    request_url: str

    @classmethod
    def from_json(cls, json: T_JSON_DICT) -> 'CertificateError':
        return cls(
            event_id=int(json['eventId']),
            error_type=str(json['errorType']),
            request_url=str(json['requestURL'])
        )


@event_class('Security.securityStateChanged')
@dataclass
class SecurityStateChanged:
    '''
    The security state of the page changed.
    '''
    #: Security state.
    security_state: 'SecurityState'
    #: True if the page was loaded over cryptographic transport such as HTTPS.
    scheme_is_cryptographic: bool
    #: List of explanations for the security state. If the overall security state is `insecure` or
    #: `warning`, at least one corresponding explanation should be included.
    explanations: typing.List['SecurityStateExplanation']
    #: Information about insecure content on the page.
    insecure_content_status: 'InsecureContentStatus'
    #: Overrides user-visible description of the state.
    summary: typing.Optional[str]

    @classmethod
    def from_json(cls, json: T_JSON_DICT) -> 'SecurityStateChanged':
        return cls(
            security_state=SecurityState.from_json(json['securityState']),
            scheme_is_cryptographic=bool(json['schemeIsCryptographic']),
            explanations=[SecurityStateExplanation.from_json(i) for i in json['explanations']],
            insecure_content_status=InsecureContentStatus.from_json(json['insecureContentStatus']),
            summary=str(json['summary']) if 'summary' in json else None
        )
