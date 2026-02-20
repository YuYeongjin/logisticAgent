package org.agent.config.mybatis;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

import javax.sql.DataSource;


@ConditionalOnProperty(
        prefix = "spring.datasource.hikari",
        name = {"wallet.username"},
        matchIfMissing = false
    )
@Configuration
@MapperScan(value= "org.agent.database.dao", sqlSessionFactoryRef = "walletSqlSessionFactory")
@EnableTransactionManagement
public class MyBatisWalletConfiguration {

    @Bean
    @Qualifier("walletHikariConfig")

    @ConfigurationProperties(prefix = "spring.datasource.hikari.wallet")
    @ConditionalOnProperty(
        prefix = "spring.datasource.hikari",
        name = {"wallet.username"},
        matchIfMissing = false
    )
    public HikariConfig walletHikariConfig() {
        return new HikariConfig();
    }

    @Bean
    @Qualifier("walletDataSource")
    @ConditionalOnBean(name = "walletHikariConfig")
    public DataSource walletDataSource() throws Exception {
        return new HikariDataSource(walletHikariConfig());
    }
    
    @Bean(name = "walletTransactionManager")
    @ConditionalOnBean(name = "walletDataSource")
    public PlatformTransactionManager walletTransactionManager(
            @Qualifier("walletDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

	
    @Bean(name = "walletSqlSessionFactory")
    @ConditionalOnBean(name = "walletDataSource")
    public SqlSessionFactory sqlSessionFactory(
            @Qualifier("walletDataSource") DataSource dataSource, ApplicationContext applicationContext) throws Exception {
    	 SqlSessionFactoryBean sqlSessionFactoryBean = new SqlSessionFactoryBean();
         sqlSessionFactoryBean.setDataSource(dataSource);
         PathMatchingResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();

         // MyBatis 설정 파일 경로 설정
         sqlSessionFactoryBean.setConfigLocation(applicationContext.getResource("classpath:mybatis-config.xml"));

      // 매퍼 XML 파일 경로 설정
         sqlSessionFactoryBean.setMapperLocations(
                         resolver.getResources("classpath*:mappers/**/*.xml")
         );
         
        return sqlSessionFactoryBean.getObject();
    }

    @Bean(name = "walletSqlSessionTemplate")
    @ConditionalOnBean(name = "walletSqlSessionFactory")
    public SqlSessionTemplate sqlSessionTemplate(
            @Qualifier("walletSqlSessionFactory") SqlSessionFactory sqlSessionFactory) {
        return new SqlSessionTemplate(sqlSessionFactory);
    }
}


