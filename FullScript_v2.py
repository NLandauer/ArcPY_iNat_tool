# Noelle Landauer
# GEO 242, 5/25/24, Final Project
# arcpy script tool to create a species range map using data from iNaturalist

import arcpy
import requests


# Generic taxon query via the iNaturalist API
# Limited to Oregon (place=10)
# Limited to most recent 1000 research-grade observations
def get_inat_observations(taxon_name, place=10):
    base_url = "https://api.inaturalist.org/v1/observations"

    # in order to calculate the proper number of pages, need to get total number of observations for your query
    # an error occurs if there are more pages than observations to fill them
    # inat limits to 200 observations per page
    count_params = {"place_id": place,
                    "taxon_name": taxon_name,
                    "per_page": 1,
                    "quality_grade": "research"}
    obs_count = requests.get(base_url, params=count_params).json()['total_results']

    # limit to 1000 observations, because inat requires an authentication token for a high number of page requests
    if obs_count <= 1000:
        pages = (obs_count // 200) + 1
    else:
        pages = 5

    # get the actual observations, up to 1000 research grade obs in Oregon
    # loop through pages, then loop through observations within each page
    # geojson points and species go into different lists for now
    page_counter = 1
    point_list = []
    species_list = []
    while page_counter <= pages:
        obs_params = {"place_id": place,
                      "taxon_name": taxon_name,
                      "page": page_counter,
                      "per_page": 200,
                      "quality_grade": "research"}
        obs = requests.get(base_url, params=obs_params).json()['results']
        for ob in obs:
            point_list.append(ob['geojson'])
            species_list.append(ob['taxon']['name'])
        page_counter += 1
    return point_list, species_list


# Create an empty feature class in gdb of choice, returns feature class object
def create_fc(gdb, fc_name):
    fc = arcpy.management.CreateFeatureclass(gdb,
                                             fc_name,
                                             geometry_type='POINT',
                                             spatial_reference=4326)
    return fc


# retrieves geojson dictionary from each observation
# retrieves x, y coordinates from the geojson in each obs, creates a Point feature, inserts in feature class
def create_points(pt_list, fc):
    for pt in pt_list:
        with arcpy.da.InsertCursor(fc, ['SHAPE@XY']) as cursor:
            for row in fc:
                pt_x = pt['coordinates'][0]
                pt_y = pt['coordinates'][1]
                point = arcpy.Point(pt_x, pt_y)
                cursor.insertRow([point])


# Adds the species data to each point in the attribute table of point_fc
def update_taxon(species_list, fc):
    # Add a new field for species to the fc
    field = "Taxon"
    arcpy.management.AddField(fc, field, field_type='TEXT')

    # Update the blank field with taxon information from species_list
    pointer = 0
    with arcpy.da.UpdateCursor(fc, [field]) as cursor:
        for row in cursor:
            row[0] = species_list[pointer]
            pointer += 1
            cursor.updateRow(row)


# create polygon around points using MinimumBoundingGeometry()
def create_mbd_polygon(points_fc, out_fc):
    arcpy.management.MinimumBoundingGeometry(points_fc,
                                             out_fc,
                                             geometry_type='CONVEX_HULL')


# Buffer() to create a distance around the outermost points
def create_buffer(out_fc, in_feat, dist='5 Miles'):
    arcpy.analysis.Buffer(in_features=in_feat,
                          out_feature_class=out_fc,
                          buffer_distance_or_field=dist,
                          line_side="FULL",
                          line_end_type="ROUND",
                          dissolve_option="ALL",
                          dissolve_field=None,
                          method="GEODESIC")


# Delete the MinimumBoundingGeometry polygon
def delete_feature(fc):
    arcpy.management.Delete(fc)


# ******* INPUTS *******

# script tool inputs
gdb = arcpy.GetParameterAsText(0)
taxon = arcpy.GetParameterAsText(1)
point_fc_name = arcpy.GetParameterAsText(2)
buffer_fc = arcpy.GetParameterAsText(3)
buffer_distance = arcpy.GetParameterAsText(4)

# test data inputs
# gdb = (r"C:\Users\noell\OneDrive\Documents\Classes\GEO242 GIS Programming\Final Project "
#        r"242\SpeciesRangeMap_FinalProject\SpeciesRangeMap_FinalProject.gdb")
# taxon = "Rubus ursinus"
# point_fc_name = 'ursinus'
# buffer_fc = "urs_buf"
# buffer_distance = "10 Miles"


# ******** RUN SCRIPT *********

# set workspace
arcpy.env.workspace = gdb

# get observations in a taxon (Oregon only, limit 1000 obs)
point_list, species_list = get_inat_observations(taxon)

# test to see if any observations were returned
# if not, stop program and send error message
if len(point_list) == 0:
    arcpy.AddError("Taxon not found, no observations were returned.")
else:
    pass

# create empty feature class for points
point_fc = create_fc(gdb, point_fc_name)

# create points from geojson and populate the feature class
create_points(point_list, point_fc)

# update the points data with associated species information
update_taxon(species_list, point_fc)

# send the feature class object back to the script tool, where it is configured as an output
arcpy.SetParameter(5, point_fc)  # 5 is the parameter index
arcpy.AddMessage("Point observations added to geodatabase and map.")

# Optional buffer polygon around points
if buffer_fc == "":
    arcpy.AddMessage("Processes completed.")
else:
    # create minimum bounding polygon from the points
    temp_poly_name = "Bounding_polygon"
    create_mbd_polygon(point_fc, temp_poly_name)

    # create buffer around bounding polygon
    create_buffer(buffer_fc, temp_poly_name, dist=buffer_distance)

    # delete bounding polygon
    delete_feature(temp_poly_name)

    # final message
    arcpy.AddMessage("Species range polygon added.")
