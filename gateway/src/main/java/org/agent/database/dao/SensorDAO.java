package org.agent.database.dao;

import org.agent.database.dto.SensorDTO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;
import java.util.Map;

@Mapper
public interface SensorDAO {
    void insertData(SensorDTO data);

    List<Map<String, Object>> getAll();

    Map<String,String> getAvgData(String location, String start_time);

    void insertLog(String logLevel, Double diffScore, String message, String source);

    Map<String,Object>  getSensorTemperature();

    Map<String,Object>  getSensorHumidity();

    Boolean updateMinTemperature(String location, Integer temperature);
    Boolean updateMaxTemperature(String location, Integer temperature);
    Boolean updateMinHumidity(String location, Integer humidity);
    Boolean updateMaxHumidity(String location, Integer humidity);
}