from django.db import models

class ChargePoint(models.Model):
    cp_id = models.CharField(max_length=50, unique=True)
    vendor = models.CharField(max_length=50, null=True, blank=True)
    model = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=50, default='Unknown')
    last_seen = models.DateTimeField(null=True, blank=True) 
    def __str__(self):
        return self.cp_id


class Transaction(models.Model):
    cp = models.ForeignKey(ChargePoint, on_delete=models.CASCADE)
    connector_id = models.IntegerField(default=1)
    transaction_id = models.IntegerField(default=1)
    started_at = models.DateTimeField()
    stopped_at = models.DateTimeField(null=True, blank=True)
    meter_start = models.FloatField(null=True, blank=True)
    meter_stop = models.FloatField(null=True, blank=True)
    energy_Wh = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.cp.cp_id}-TX{self.transaction_id}"


class MeterValue(models.Model):
    cp = models.ForeignKey(ChargePoint, on_delete=models.CASCADE)
    ts = models.DateTimeField()
    power_W = models.FloatField(null=True, blank=True)
    energy_Wh = models.FloatField(null=True, blank=True)
    current_A = models.FloatField(null=True, blank=True)
    voltage_V = models.FloatField(null=True, blank=True)
    soc_percent = models.FloatField(null=True, blank=True)
    raw = models.JSONField(default=dict)


class EventLog(models.Model):
    cp = models.ForeignKey(ChargePoint, on_delete=models.CASCADE)
    direction = models.CharField(max_length=10, choices=[('IN','IN'),('OUT','OUT')])
    action = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    unique_id = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.cp.cp_id} {self.direction} {self.action}"


class FuzzJob(models.Model):
    scenario = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default='idle')
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Job-{self.id} ({self.scenario})"


class ControlCommand(models.Model):
    cp_id   = models.CharField(max_length=50)
    type    = models.CharField(max_length=50)  # e.g. 'fuzz_start', 'fuzz_stop', 'remote_start', ...
    payload = models.JSONField(default=dict)

    # ★ 추가
    status  = models.CharField(
        max_length=16,
        choices=[("queued","queued"),("sent","sent"),("done","done"),("error","error")],
        default="queued",
    )
    

    created_at = models.DateTimeField(auto_now_add=True)
