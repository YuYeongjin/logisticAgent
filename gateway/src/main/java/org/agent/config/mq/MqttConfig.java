package org.agent.config.mq;

import org.agent.service.mqtt.MqttService;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.endpoint.MessageProducerSupport;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
public class MqttConfig {

    public final MqttService mqttService;

    public MqttConfig(MqttService mqttService) {
        this.mqttService = mqttService;
    }

    @Bean
    public MqttPahoClientFactory mqttClientFactory() {
        DefaultMqttPahoClientFactory factory = new DefaultMqttPahoClientFactory();
        MqttConnectOptions options   = new MqttConnectOptions();
        options.setServerURIs(new String[]{"tcp://192.168.10.20:1883"});
        options.setCleanSession(true);

        factory.setConnectionOptions(options);

        return factory;
    }

    @Bean
    public MessageChannel mqttInputChannel() {
        return new DirectChannel();
    }

//    @Bean
//    public MessageProducerSupport mqttInbound() {
//        MqttPahoMessageDrivenChannelAdapter adapter =
//                new MqttPahoMessageDrivenChannelAdapter("testClient", mqttClientFactory(),
//                        "test/topic");
//        adapter.setOutputChannel(mqttInputChannel());
//        return adapter;
//    }

    @Bean
    public MessageProducerSupport mqttInbound() {
        // ID 뒤에 현재 시간을 붙여 중복 방지
        String uniqueClientId = "testClient_" + System.currentTimeMillis();
        MqttPahoMessageDrivenChannelAdapter adapter =
                new MqttPahoMessageDrivenChannelAdapter(uniqueClientId, mqttClientFactory(), "test/topic");
        adapter.setOutputChannel(mqttInputChannel());
        return adapter;
    }
    @Bean
    @ServiceActivator(inputChannel = "mqttInputChannel")
    public MessageHandler handler() {
        return message -> {
//            System.out.println("Received message: " + message.getPayload());
            String payload = (String) message.getPayload();

            mqttService.handleMessage(payload);
        };
    }

}
