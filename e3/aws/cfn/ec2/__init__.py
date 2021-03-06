from e3.aws.cfn import Resource, AWSType, GetAtt
from e3.aws.ec2.ami import AMI


class BlockDevice(object):
    """Block device for EC2 instances."""

    pass


class EphemeralDisk(BlockDevice):
    """Ephemeral disk."""

    def __init__(self, device_name, id=0):
        """Initialize an ephemeral disk.

        :param device_name: name of the device associated with that disk
        :type device_name: str
        :param id: id of the ephemeral disk (default is 0)
        :type id: int
        """
        assert isinstance(id, int)
        self.device_name = device_name
        self.id = id

    @property
    def properties(self):
        """Serialize the object as a simple dict.

        Can be used to transform to CloudFormation Yaml format.

        :rtype: dict
        """
        return {"DeviceName": self.device_name,
                "VirtualName": "ephemeral%s" % self.id}


class EBSDisk(BlockDevice):
    """EBS Disk."""

    def __init__(self, device_name, size=20):
        """Initialize an EBS disk.

        :param device_name: name of the device associated with that disk
        :type device_name: str
        :param size: disk size in Go (default: 20Go)
        :type size: int
        """
        self.device_name = device_name
        self.size = size

    @property
    def properties(self):
        """Serialize the object as a simple dict.

        Can be used to transform to CloudFormation Yaml format.

        :rtype: dict
        """
        return {"DeviceName": self.device_name,
                "Ebs": {"VolumeSize": str(self.size),
                        "VolumeType": "standard"}}


class NetworkInterface(object):
    """EC2 Instance network interface."""

    def __init__(self,
                 subnet,
                 public_ip=False,
                 groups=None,
                 device_index=None,
                 description=None):
        """Initialize a NetworkInterface.

        :param subnet: subnet to which the interface is attached
        :type subnet: e3.aws.cfn.ec2.Subnet
        :param public_ip: if True assign automatically public IP address.
            Default is False.
        :type public_ip: bool
        :param groups: list of security groups associated with the interface.
            If no group is specified, AWS will assign a default group.
        :type groups: list[SecurityGroup] | None
        :param device_index: natural giving the interface position. 0 is the
            default interface. If set to None, some method such as
            e3.aws.cfn.ec2.Instance.add will assign automatically a device
            index
        :type device_index: 0 | None
        :param description: optional description
        :type description: str | None
        """
        assert isinstance(subnet, Subnet)
        self.subnet = subnet
        self.public_ip = public_ip
        self.groups = groups
        self.device_index = device_index
        self.description = description

    @property
    def properties(self):
        """Serialize the object as a simple dict.

        Can be used to transform to CloudFormation Yaml format.

        :rtype: dict
        """
        result = {'AssociatePublicIpAddress': self.public_ip,
                  'SubnetId': self.subnet.ref,
                  'DeleteOnTermination': True}
        if self.device_index is not None:
            result['DeviceIndex'] = self.device_index
        if self.groups:
            result['GroupSet'] = [group.ref for group in self.groups]
        if self.description is not None:
            result['Description'] = self.description
        return result


class Instance(Resource):
    """EC2 Instance."""

    ATTRIBUTES = ('AvailabilityZone',
                  'PrivateDnsName',
                  'PublicDnsName',
                  'PrivateIp',
                  'PublicIp')

    def __init__(self, name, image,
                 instance_type='t2.micro',
                 disk_size=None):
        """Initialize an EC2 instance.

        :param name: logical name of the instance
        :type name: str
        :param image: AMI to use
        :type image_id: e3.aws.ec2.ami.AMI
        :param instance_type: kind of instance (default t2.micro)
        :type instance_type: str
        :param disk_size: size of disk. If None the disk size will be
            the original AMI one. Note that this affect only the root
            device of the AMI
        :type disk_size: int | None
        """
        super(Instance, self).__init__(name, kind=AWSType.EC2_INSTANCE)
        assert isinstance(image, AMI)
        self.image = image
        self.instance_type = instance_type
        self.block_devices = []
        if disk_size is not None:
            self.add(EBSDisk(device_name=self.image.root_device,
                             size=disk_size))
        self.instance_profile = None
        self.network_interfaces = {}

    @property
    def public_ip(self):
        """Return a reference to the public Ip.

        :rtype: e3.aws.cfn.GetAtt
        """
        return GetAtt(self.name, 'PublicIp')

    def set_instance_profile(self, profile):
        self.instance_profile = profile

    def add(self, device):
        """Add a device to the instance.

        :param device: can be a disk or a network interface
        :type device: NetworkInterface | BockDevice
        :return: the Instance itself
        :rtype: Instance
        """
        if isinstance(device, NetworkInterface):
            if device.device_index is None:
                # Assign automatically a device index
                index = max(list(self.network_interfaces.keys()) + [0]) + 1
                device.device_index = index
            else:
                # Ensure the device is not already present
                assert device.device_index not in self.network_interfaces
                index = device.device_index

            self.network_interfaces[index] = device
        elif isinstance(device, BlockDevice):
            self.block_devices.append(device)
        else:
            assert False, 'invalid device %s' % device
        return self

    @property
    def properties(self):
        """Serialize the object as a simple dict.

        Can be used to transform to CloudFormation Yaml format.

        :rtype: dict
        """
        result = {'ImageId': self.image.id,
                  'InstanceType': self.instance_type,
                  'BlockDeviceMappings': [bd.properties
                                          for bd in self.block_devices]}
        if self.instance_profile is not None:
            result['IamInstanceProfile'] = self.instance_profile.ref
        if self.network_interfaces:
            result['NetworkInterfaces'] = \
                [ni.properties
                 for ni in self.network_interfaces.values()]
        return result


class VPC(Resource):
    """EC2 VPC."""

    ATTRIBUTES = ('CidrBlock',
                  'CidrBlockAssociations',
                  'DefaultNetworkAcl',
                  'DefaultSecurityGroup',
                  'Ipv6CidrBlocks')

    def __init__(self, name, cidr_block):
        """Initialize a VPC.

        :param name: logical name in stack
        :type name: str
        :param cidr_block: IPv4 address range
        :type cidr_block: str
        """
        super(VPC, self).__init__(name, kind=AWSType.EC2_VPC)
        self.cidr_block = cidr_block

    @property
    def properties(self):
        return {'CidrBlock': self.cidr_block}

    @property
    def cidrblock(self):
        return self.getatt('CidrBlock')


class Subnet(Resource):
    """EC2 subnet."""

    def __init__(self, name, vpc, cidr_block):
        """Initialize a subnet.

        :param name: logical name in stack
        :type name: str
        :param vpc: vpc in which the subnet should be created
        :type vpc: VPC
        :param cidr_block: IPv4 address range
        :type cidr_block: str
        """
        super(Subnet, self).__init__(name, kind=AWSType.EC2_SUBNET)
        self.cidr_block = cidr_block
        assert isinstance(vpc, VPC)
        self.vpc = vpc

    @property
    def properties(self):
        return {'CidrBlock': self.cidr_block,
                'VpcId': self.vpc.ref}


class InternetGateway(Resource):
    """EC2 Internet gateway."""

    def __init__(self, name):
        """Initialize an internet gateway.

        :param name: logical name in stack
        :type name: str
        """
        super(InternetGateway, self).__init__(
            name, kind=AWSType.EC2_INTERNET_GATEWAY)


class VPCGatewayAttachment(Resource):
    """EC2 VPCGatewayAttachment."""

    def __init__(self, name, vpc, gateway):
        """Initialize an attachment between a gateway and a VPC.

        :param name: logical name in stack
        :type name: str
        :param vpc: vpc in which the subnet should be created
        :type vpc: VPC
        :param gateway: a gateway
        :type gateway: InternetGateway
        """
        super(VPCGatewayAttachment, self).__init__(
            name, kind=AWSType.EC2_VPC_GATEWAY_ATTACHMENT)
        assert isinstance(vpc, VPC)
        assert isinstance(gateway, InternetGateway)
        self.vpc = vpc
        self.gateway = gateway

    @property
    def properties(self):
        return {'VpcId': self.vpc.ref,
                'InternetGatewayId': self.gateway.ref}


class RouteTable(Resource):
    """EC2 Route Table."""

    def __init__(self, name, vpc, tags=None):
        """Initialize a route table.

        :param name: logical name in stack
        :type name: str
        :param vpc: a VPC instance to attach the route table to.
        :type vpc: e3.aws.cfn.ec2.VPC
        :param tags: a dict of key/value tags
        :type tags: dict
        """
        super(RouteTable, self).__init__(name, kind=AWSType.EC2_ROUTE_TABLE)
        assert isinstance(vpc, VPC)
        self.vpc = vpc
        self.tags = tags

    @property
    def properties(self):
        result = {'VpcId': self.vpc.ref}
        if self.tags is not None:
            result['Tags'] = self.tags
        return result


class Route(Resource):
    """EC2 Route."""

    def __init__(self, name, route_table, dest_cidr_block,
                 gateway,
                 gateway_attach):
        """Initialize a route.

        :param name: logical name in stack
        :type name: str
        :param route_rable: a route table
        :type route_table: RouteTable
        :param dest_cidr_block: route ipv4 address range
        :type dest_cidr_block: str
        :param gateway: the gateway
        :type gateway: InternetGateway
        :param gateway_attach: a gateway attachment instance
        :type gateway_attach: VPCGatewayAttachment
        """
        super(Route, self).__init__(name, kind=AWSType.EC2_ROUTE)
        assert isinstance(route_table, RouteTable)
        assert isinstance(gateway, InternetGateway)
        self.route_table = route_table
        self.dest_cidr_block = dest_cidr_block
        self.gateway = gateway
        self.gateway_attach = gateway_attach
        self.depends = self.gateway_attach.name

    @property
    def properties(self):
        return {'RouteTableId': self.route_table.ref,
                'DestinationCidrBlock': self.dest_cidr_block,
                'GatewayId': self.gateway.ref}


class SubnetRouteTableAssociation(Resource):
    """EC2 SubnetRouteTableAssociation."""

    def __init__(self, name, subnet, route_table):
        """Initialize an association between a route table and a subnet.

        :param name: logical name in stack
        :type name: str
        :param subnet: a subnet instance to attach the route table to.
        :type subnet: e3.aws.cfn.ec2.Subnet
        :param route_rable: a route table
        :type route_table: RouteTable
        """
        super(SubnetRouteTableAssociation, self).__init__(
            name, kind=AWSType.EC2_SUBNET_ROUTE_TABLE_ASSOCIATION)
        self.subnet = subnet
        self.route_table = route_table

    @property
    def properties(self):
        return {'SubnetId': self.subnet.ref,
                'RouteTableId': self.route_table.ref}
