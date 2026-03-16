import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt

INPUT_FILE = "odew2_weekly_features.csv"
OUTPUT_FILE = "clustered_weeks.csv"

def run_pca_clustering():

    # Load dataset
    df = pd.read_csv(INPUT_FILE)

    # Select numeric features
    feature_cols = [
        "artist_entropy",
        "genre_entropy",
        "unique_artists",
        "unique_genres",
        "total_listens",
        "unique_tracks",
        "avg_listen_hour",
        "new_artists",
        "new_artist_rate"
    ]
    df = df.dropna(subset=feature_cols)

    X = df[feature_cols]

    # Normalize data
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # PCA
    pca = PCA(n_components=2)
    components = pca.fit_transform(X_scaled)

    df["PC1"] = components[:, 0]
    df["PC2"] = components[:, 1]
    loadings = pd.DataFrame(
        pca.components_,
        columns=feature_cols,
        index=["PC1", "PC2"]
    )

    print("\nPCA Feature Loadings:")
    print(loadings)

    print("Explained variance:", pca.explained_variance_ratio_)

    # K-means clustering
    kmeans = KMeans(n_clusters=4, n_init=20, random_state=42)
    df["cluster"] = kmeans.fit_predict(X_scaled)

    # Save results
    df.to_csv(OUTPUT_FILE, index=False)

    # Visualization
    plt.figure(figsize=(8,6))
    scatter = plt.scatter(df["PC1"], df["PC2"], c=df["cluster"])
    plt.colorbar(scatter, label="Cluster")
    plt.xlabel("Principal Component 1")
    plt.ylabel("Principal Component 2")
    plt.title("Music Listening Behavior Clusters")
    plt.show()
    cluster_summary = df.groupby("cluster")[feature_cols].mean()
    print("\nCluster Summary:")
    print(cluster_summary)


if __name__ == "__main__":
    run_pca_clustering()