import "leaflet";

declare module "leaflet" {
  interface MarkerClusterGroupOptions {
    chunkedLoading?: boolean;
    iconCreateFunction?: (cluster: MarkerCluster) => Icon | DivIcon;
    maxClusterRadius?: number | ((zoom: number) => number);
    showCoverageOnHover?: boolean;
    spiderfyOnMaxZoom?: boolean;
  }

  class MarkerCluster extends Marker {
    getChildCount(): number;
  }

  class MarkerClusterGroup extends FeatureGroup {
    constructor(options?: MarkerClusterGroupOptions);
  }
}
