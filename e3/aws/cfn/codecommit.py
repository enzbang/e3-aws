from e3.aws.cfn import AWSType, Resource
from e3.aws.cfn.iam import Statement
import re


class Repository(Resource):

    ATTRIBUTES = ("Arn", "CloneUrlHttp", "CloneUrlSsh", "Name")

    def __init__(self, name, description):
        resource_name = re.sub(r"[^a-zA-Z0-9]+", "", name)
        super(Repository, self).__init__(
            resource_name, kind=AWSType.CODE_COMMIT_REPOSITORY
        )
        self.name = resource_name
        self.repository_name = name
        self.description = description

    @property
    def properties(self):
        return {
            "RepositoryName": self.repository_name,
            "RepositoryDescription": self.description,
        }
