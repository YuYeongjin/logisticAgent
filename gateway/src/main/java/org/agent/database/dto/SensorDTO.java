package org.agent.database.dto;

import lombok.Data;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@Data
public class SensorDTO {
    private String location;
    private double temperature;

    private double humidity;
    private String timestamp;
    public SensorDTO(){}
    public SensorDTO(String location, double temperature, String timestamp,double humidity) {
        this.location = location;
        this.temperature = temperature;
        this.timestamp = timestamp;
        this.humidity = humidity;
    }

    public double getHumidity() {
        return humidity;
    }

    public double getTemperature() {
        return temperature;
    }

    public String getLocation() {
        return location;
    }

    public String getTimestamp() {
        return timestamp;
    }

    public void setHumidity(double humidity) {
        this.humidity = humidity;
    }

    public void setLocation(String location) {
        this.location = location;
    }

    public void setTemperature(double temperature) {
        this.temperature = temperature;
    }

    public void setTimestamp(String timestamp) {
        this.timestamp = timestamp;
    }

    @Override
    public String toString(){
        return "location : " + location + ", temperature : " + temperature + ", time: " + timestamp;
    };
}