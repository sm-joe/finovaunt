"""The privileged EC2 executor must never run through the dashboard collector."""
import sys
import types

import pytest

from scripts.nonprod_executor import execute_action, verify_ec2_target


ROLE = "arn:aws:iam::123456789012:role/Finovaunt-NonProd-Executor-Role"
ID = "i-0123456789abcdef0"


def test_executor_rejects_eks_asg_and_production_instances():
    instance = {"InstanceId": ID, "RootDeviceType": "ebs",
                "Tags": [{"Key": "Environment", "Value": "dev"}]}
    assert verify_ec2_target(instance, expected_id=ID, environment="dev")["instance_id"] == ID
    for tag in ("eks:cluster-name", "kubernetes.io/cluster/example", "aws:autoscaling:groupName"):
        with pytest.raises(ValueError):
            verify_ec2_target({**instance, "Tags": instance["Tags"] + [{"Key": tag, "Value": "managed"}]},
                              expected_id=ID, environment="dev")
    with pytest.raises(ValueError, match="non-production"):
        verify_ec2_target({**instance, "Tags": [{"Key": "Environment", "Value": "prod"}]},
                          expected_id=ID, environment="dev")


def test_privileged_execution_is_disabled_before_aws_call(monkeypatch):
    monkeypatch.delenv("FINOVAUNT_ALLOW_NONPROD_EXECUTION", raising=False)
    with pytest.raises(PermissionError, match="disabled"):
        execute_action(role_arn=ROLE, region="us-east-1", environment="dev",
                       action="stop", instance_ids=[ID], execute=True)
    with pytest.raises(ValueError, match="Executor-Role"):
        execute_action(role_arn="arn:aws:iam::123456789012:role/Finovaunt-RO-Scan-Role",
                       region="us-east-1", environment="dev", action="stop",
                       instance_ids=[ID], execute=True)


def test_executor_plan_does_not_call_mutation(monkeypatch):
    events = []
    class STS:
        def assume_role(self, **kwargs):
            events.append("assume_role")
            return {"Credentials": {"AccessKeyId": "fake", "SecretAccessKey": "fake", "SessionToken": "fake"}}
        def get_caller_identity(self):
            return {"Account": "123456789012",
                    "Arn": "arn:aws:sts::123456789012:assumed-role/Finovaunt-NonProd-Executor-Role/test"}
    class EC2:
        def describe_instances(self, **kwargs):
            events.append("describe")
            return {"Reservations": [{"Instances": [
                {"InstanceId": ID, "RootDeviceType": "ebs", "State": {"Name": "running"},
                 "Tags": [{"Key": "Environment", "Value": "dev"}]}
            ]}]}
        def stop_instances(self, **kwargs):
            raise AssertionError("Stop must not be called during planning.")
        def start_instances(self, **kwargs):
            raise AssertionError("Start must not be called during planning.")
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(
        client=lambda name, **kwargs: STS() if name == "sts" else EC2(),
    ))
    result = execute_action(role_arn=ROLE, region="us-east-1",
                            environment="dev", action="stop", instance_ids=[ID])
    assert result["executed"] is False
    assert events == ["assume_role", "describe"]
