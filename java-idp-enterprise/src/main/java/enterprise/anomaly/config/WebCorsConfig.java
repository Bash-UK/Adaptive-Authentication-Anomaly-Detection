package enterprise.anomaly.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/enterprise/**")
            .allowedOrigins("http://localhost:8088", "http://127.0.0.1:8088")
            .allowedMethods("GET", "POST", "OPTIONS")
            .allowedHeaders("*");
    }
}
