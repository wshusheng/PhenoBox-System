package at.gmi.djamei.util;

import java.nio.file.Path;
import java.nio.file.Paths;

import at.gmi.djamei.config.Config;



public class PathUtil {
	private PathUtil(){}
	
	//TODO Error handling for malformed paths
	public static Path getLocalPathFromSmbUrl(String url){
		//TODO sanitize and remove e.g: /../ entries
		int index = url.indexOf('/');
		for(int i=0; i<3;i++){
			index = url.indexOf('/', index + 1);
		}
		
		Path mountPoint = Paths.get(Config.INSTANCE.getLocalPathFromSmbUrl(url.substring(0, index+1)));
		if (mountPoint!=null){
			if(url.length()>index){
				String[] parts = url.substring(index+1, url.length()).split("/");
				for(int i=0; i<parts.length; i++){
					mountPoint = mountPoint.resolve(parts[i]);	
				}
			}
			return mountPoint;
		}
		return null;
	}
	public static String getSmbUrlFromLocalPath(Path path){
		return Config.INSTANCE.getSmbUrlFromLocalPath(path.toString());
	}
	public static String toFilename(String s){
		return s.replaceAll("[^A-Za-z0-9 ]", "").replaceAll("[ ]", "_");
	}
}
