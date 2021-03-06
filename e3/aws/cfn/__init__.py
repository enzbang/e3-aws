from e3.aws import client
from enum import Enum
import re
import yaml


VALID_STACK_NAME = re.compile('^[a-zA-Z][a-zA-Z0-9-]*$')
VALID_STACK_NAME_MAX_LEN = 128


class AWSType(Enum):
    """Cloud Formation resource types."""

    EC2_INSTANCE = 'AWS::EC2::Instance'
    EC2_INTERNET_GATEWAY = 'AWS::EC2::InternetGateway'
    EC2_ROUTE = 'AWS::EC2::Route'
    EC2_ROUTE_TABLE = 'AWS::EC2::RouteTable'
    EC2_SECURITY_GROUP = 'AWS::EC2::SecurityGroup'
    EC2_SUBNET = 'AWS::EC2::Subnet'
    EC2_SUBNET_ROUTE_TABLE_ASSOCIATION = \
        'AWS::EC2::SubnetRouteTableAssociation'
    EC2_VOLUME = 'AWS::EC2::Volume'
    EC2_VPC = 'AWS::EC2::VPC'
    EC2_VPC_GATEWAY_ATTACHMENT = 'AWS::EC2::VPCGatewayAttachment'
    IAM_ROLE = 'AWS::IAM::Role'
    IAM_POLICY = 'AWS::IAM::Policy'
    IAM_INSTANCE_PROFILE = 'AWS::IAM::InstanceProfile'
    ROUTE53_RECORDSET = 'AWS::Route53::RecordSet'
    S3_BUCKET = 'AWS::S3::Bucket'


class GetAtt(object):
    """Intrinsic function Fn::Getatt."""

    def __init__(self, name, attribute):
        """Initialize a Getatt instance.

        :param name: resource name
        :type name: str
        :param attribute: attribute name
        :type attribute: str
        """
        self.name = name
        self.attribute = attribute


class Ref(object):
    """Intrinsic function Fn::Ref."""

    def __init__(self, name):
        """Initialize a reference.

        :param name: resource name
        :type name: str
        """
        self.name = name


class Base64(object):
    """Intrinsic function Fn::Base64."""

    def __init__(self, content):
        """Initialize a base64 content.

        :param content: content to be encoded into base64
        :type content: str
        """
        self.content = content


# Declare Yaml representer for intrinsic functions

def getatt_representer(dumper, data):
    return dumper.represent_scalar(
        '!GetAtt', '%s.%s' % (data.name, data.attribute))


def ref_representer(dumper, data):
    return dumper.represent_scalar('!Ref', data.name)


def base64_representer(dumper, data):
    return dumper.represent_scalar('!Base64', data.content)


yaml.add_representer(GetAtt, getatt_representer)
yaml.add_representer(Ref, ref_representer)
yaml.add_representer(Base64, base64_representer)


class Resource(object):
    """A CloudFormation resource."""

    # List of valid attribute names
    ATTRIBUTES = ()

    def __init__(self, name, kind):
        """Initialize a resource.

        :param name: name of the resource (alphanumeric)
        :type name: str
        :param kind: resource kind
        :type kind: e3.aws.cfn.types.AWSType
        """
        assert isinstance(kind, AWSType), \
            'resource kind should be an AWSType: found %s' % kind
        assert name.isalnum(), \
            'resource name should be alphanumeric: found %s' % name
        self.name = name
        self.kind = kind
        self.depends = None

    def getatt(self, name):
        """Return an attribute reference.

        :param name: attribute name. should one of the valid attribute
            declared in ATTRIBUTES class variable
        :type name: str
        :return: a getatt object
        :rtype: e3.aws.cfn.types.GetAtt

        """
        assert name in self.ATTRIBUTES, 'invalid attribute %s' % name
        return GetAtt(self.name, name)

    @property
    def ref(self):
        """Return a reference to the current resource.

        :return: a reference
        :rtype: e3.aws.cfn.types.Ref
        """
        return Ref(self.name)

    @property
    def properties(self):
        """Return the resource properties dict.

        :return: the resources Properties key value for the current resource.
        :rtype: dict
        """
        return {}

    def export(self):
        """Export resource as a template fragment.

        :return: the dict representing the resources. The resulting dict can
            be serialized using Yaml to get a valid CloudFormation template
            fragment
        :rtype: dict
        """
        result = {'Type': self.kind.value,
                  'Properties': self.properties}
        if self.depends is not None:
            result['DependsOn'] = self.depends
        return result


class Stack(object):
    """A CloudFormation stack."""

    def __init__(self, name, description=None):
        """Initialize a stack.

        :param name: stack name
        :type name: str
        :param description: a description of the stack
        :type description: str | None
        """
        assert re.match(VALID_STACK_NAME, name) and \
            len(name) <= VALID_STACK_NAME_MAX_LEN, \
            'invalid stack name: %s' % name
        self.resources = {}
        self.name = name
        self.description = description

    def add(self, element):
        """Add a resource or merge a stack.

        :param element: if a resource add the resource to the stack. If a stack
            merge its resources into the current stack.
        :type element: Stack | Resources
        :return: the current stack
        :rtype: Stack
        """
        assert isinstance(element, Resource) or isinstance(element, Stack), \
            "a resource or a stack is expected. got %s" % element
        if isinstance(element, Resource):
            assert element.name not in self.resources, \
                'resource already exist: %s' % element.name
            self.resources[element.name] = element
        else:
            for resource in element.resources.values():
                assert element.name not in self.resources, \
                    'resource already exist: %s' % resource.name
                self.resources[resource.name] = resource
        return self

    def __iadd__(self, element):
        """Add a resource or merge a stack.

        :param element: if a resource add the resource to the stack. If a stack
            merge its resources into the current stack.
        :type element: Stack | Resources
        :return: the current stack
        :rtype: Stack
        """
        return self.add(element)

    def __getitem__(self, key):
        if key not in self.resources:
            raise KeyError
        return self.resources[key]

    def export(self):
        """Export stack as dict.

        :return: a dict that can be serialized as YAML to produce a template
        :rtype: dict
        """
        result = {
            'AWSTemplateFormatVersion': '2010-09-09',
            'Resources': {v.name: v.export()
                          for v in list(self.resources.values())}}
        if self.description is not None:
            result['Description'] = self.description
        return result

    @property
    def body(self):
        """Export stack as a CloudFormation template.

        :return: a valid CloudFormation template
        :rtype: str
        """
        return yaml.dump(self.export())

    @client('cloudformation')
    def create(self, client):
        """Create a stack.

        :param region: region in which to create the stack. If None the
            default region is used.
        :type region: str | None
        """
        return client.create_stack(StackName=self.name,
                                   TemplateBody=self.body,
                                   Capabilities=['CAPABILITY_IAM'])

    @client('cloudformation')
    def create_change_set(self, client, name):
        """Create a change set.

        This creates a difference between the state of the stack on AWS servers
        and the current one generated with e3-aws.

        :param client: a botocore client
        :type client: botocore.client.Client
        :param name: name of the changeset
        :type name: str
        """
        return client.create_change_set(ChangeSetName=name,
                                        StackName=self.name,
                                        TemplateBody=self.body,
                                        Capabilities=['CAPABILITY_IAM'])

    @client('cloudformation')
    def delete(self, client):
        """Delete a stack.

        Delete a stack. Note that operation is aynchron

        :param client: a botocore client
        :type client: botocore.client.Client
        """
        return client.delete_stack(StackName=self.name)

    @client('cloudformation')
    def cost(self, client):
        """Compute cost of the stack (estimation).

        :param client: a botocore client
        :type client: botocore.client.BaseClient
        """
        return client.estimate_template_cost(TemplateBody=self.body)

    @client('cloudformation')
    def resource_status(self, client, in_progress_only=True):
        """Return status of each resources of the stack.

        The state of the stack taken is the one pushed on AWS (after a call
        to create for example).

        :param client: a botocore client
        :type client: botocore.client.BaseClient
        :param in_progress_only: if True return only resources that are in
            one of the "PROGRESS" state (deletion, creation, ...)
        :type in_progress_only: bool
        :return: a dict associating a resource logical name to a status name
        :rtype: dict
        """
        aws_result = client.describe_stack_resources(StackName=self.name)
        assert 'StackResources' in aws_result
        result = {}
        for res in aws_result['StackResources']:
            if 'PROGRESS' in res['ResourceStatus'] or not in_progress_only:
                result[res['LogicalResourceId']] = res['ResourceStatus']
        return result
