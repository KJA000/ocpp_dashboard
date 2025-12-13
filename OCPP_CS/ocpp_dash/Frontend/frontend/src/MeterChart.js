import React from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

export default function MeterChart({ data }) {
  return (
    <LineChart width={700} height={320} data={data}>
      <CartesianGrid strokeDasharray="4 4" />
      <XAxis dataKey="ts" />
      <YAxis />
      <Tooltip />
      <Line type="monotone" dataKey="power_W" name="Power (W)" />
      <Line type="monotone" dataKey="voltage_V" name="Voltage (V)" />
    </LineChart>
  );
}
