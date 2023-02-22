import pathlib
import re
from typing import Dict, List, Optional, TypedDict
import boto3
import json
import yaml
from ansible_collections.ansible.content_builder.plugins.plugin_utils.cloud_utils import generator
from ansible_collections.ansible.content_builder.plugins.plugin_utils.cloud_utils.utils import (
    camel_to_snake,
    PluginsInputValidator,
    CollectionInputValidator
)
from ansible.plugins.action import ActionBase

class Schema(TypedDict):
    """A type for the JSONSchema spec"""

    typeName: str
    description: str
    properties: Dict
    definitions: Optional[Dict]
    required: Optional[List]
    primaryIdentifier: List
    readOnlyProperties: Optional[List]
    createOnlyProperties: Optional[List]
    taggable: Optional[bool]
    handlers: Optional[Dict]


def generate_schema(raw_content) -> Dict:
    json_content = json.loads(raw_content)
    schema: Dict[str, Schema] = json_content

    for key, value in schema.items():
        if key != "anyOf":
            if isinstance(value, list):
                elems = []
                for v in value:
                    if isinstance(v, list):
                        elems.extend(
                            [camel_to_snake(p.split("/")[-1].strip()) for p in v]
                        )
                    else:
                        elems.append(camel_to_snake(v.split("/")[-1].strip()))

                schema[key] = elems

    return schema


class ActionModule(ActionBase):
    
    def __init__(self, *args, **kwargs):
        super(ActionModule, self).__init__(*args, **kwargs)
        self._validator_name = None
        self._result = {}

    def _debug(self, name, msg):
        """Output text using ansible's display
        :param msg: The message
        :type msg: str
        """
        msg = "<{phost}> {name} {msg}".format(phost=self._playhost, name=name, msg=msg)
        self._display.vvvv(msg)

    def run(self, tmp=None, task_vars=None):
        """The std execution entry pt for an action plugin
        :param tmp: no longer used
        :type tmp: none
        :param task_vars: The vars provided when the task is run
        :type task_vars: dict
        :return: The results from the parser
        :rtype: dict
        """

        self._result = super(ActionModule, self).run(tmp, task_vars)
        self._task_vars = task_vars

        args = self._task.args

        input_vars_collection =task_vars["collection"]
        input_vars_plugins = task_vars["plugins"][0]

        PluginsInputValidator(**input_vars_plugins)
        CollectionInputValidator(**input_vars_collection)

        RESOURCES = []
        resource_file = pathlib.Path(args.get("resource") + "/modules.yaml")
        res = resource_file.read_text()
        for i in yaml.safe_load(res):
            RESOURCES = i.get("RESOURCES", "")
            if RESOURCES:
                break
        for type_name in RESOURCES:
            print("Collecting Schema")
            print(type_name)
            cloudformation = generator.CloudFormationWrapper(boto3.client("cloudformation"))
            raw_content = cloudformation.generate_docs(type_name)
            schema = generate_schema(raw_content)
            file_name = re.sub("::", "_", type_name)
            if not pathlib.Path(args.get("api_object_path")).exists():
                pathlib.Path(args.get("api_object_path")).mkdir(parents=True, exist_ok=True)
            schema_file = pathlib.Path(args.get("api_object_path") + "/" + file_name + ".json")
            schema_file.write_text(json.dumps(schema, indent=2))
        return self._result
